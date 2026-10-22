"""Адаптивный тест уровня. Проверку ответов и итоговый уровень считает только бэкенд.

Алгоритм «лесенка»: на каждом уровне до 3 вопросов, уровень сдан при 2 верных.
Сдал — поднимаемся, не сдал — спускаемся. Тест заканчивается, когда найдена граница:
уровень сдан, а следующий за ним не сдан (или выше некуда / ниже некуда).

Для итогового уровня B1 и выше добавляется письменное задание. Его оценивает ИИ
(apps.assessment.writing), а здесь оценка сводится с результатом теста:
письмо может понизить уровень, но не поднять выше результата теста.
"""

import random
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.models import LEVEL_ORDER, Level, level_index
from apps.leads.models import Lead

from .models import Question, TestAnswer, TestSession, WritingTask

TEST_LEVELS = LEVEL_ORDER[1:]  # A1..C1; A0 — «не сдал A1»
QUESTIONS_PER_LEVEL = 3
PASS_SCORE = 2
WRITING_FROM_LEVEL = Level.B1
SCORE_FIELDS = ("task_achievement", "grammar", "vocabulary", "coherence")


class AssessmentError(Exception):
    pass


class WrongQuestion(AssessmentError):
    pass


class NoQuestions(AssessmentError):
    pass


class InvalidState(AssessmentError):
    pass


class WritingTooShort(AssessmentError):
    def __init__(self, words: int, min_words: int):
        super().__init__(f"{words} слов, нужно не меньше {min_words}")
        self.words = words
        self.min_words = min_words


class InvalidWritingAssessment(AssessmentError):
    pass


@dataclass(frozen=True)
class NextQuestion:
    question: Question
    number: int


@dataclass(frozen=True)
class NeedWriting:
    task: WritingTask


@dataclass(frozen=True)
class Finished:
    session: TestSession


Step = NextQuestion | NeedWriting | Finished


def _level_stats(session: TestSession) -> dict[str, tuple[int, int]]:
    rows = (
        session.answers.values("question__level")
        .annotate(asked=Count("id"), correct=Count("id", filter=Q(is_correct=True)))
    )
    return {row["question__level"]: (row["asked"], row["correct"]) for row in rows}


def _verdict(asked: int, correct: int) -> str | None:
    if correct >= PASS_SCORE:
        return "pass"
    if asked - correct > QUESTIONS_PER_LEVEL - PASS_SCORE:
        return "fail"
    return None


def _start_level(declared: str) -> str:
    return declared if declared in TEST_LEVELS else Level.A1


def _next_step(session: TestSession) -> tuple[str, str]:
    """("ask", уровень) — задать вопрос этого уровня; ("done", уровень) — результат теста."""
    stats = _level_stats(session)
    verdicts = {level: _verdict(*stats.get(level, (0, 0))) for level in TEST_LEVELS}
    level = _start_level(session.declared_level)
    while True:
        verdict = verdicts[level]
        if verdict is None:
            return "ask", level
        i = TEST_LEVELS.index(level)
        if verdict == "pass":
            if i == len(TEST_LEVELS) - 1 or verdicts[TEST_LEVELS[i + 1]] == "fail":
                return "done", level
            level = TEST_LEVELS[i + 1]
        else:
            if i == 0:
                return "done", Level.A0
            if verdicts[TEST_LEVELS[i - 1]] == "pass":
                return "done", TEST_LEVELS[i - 1]
            level = TEST_LEVELS[i - 1]


def _mc_confidence(session: TestSession, mc_level: str) -> str:
    """Высокая, если на границе ответы однозначные: свой уровень без ошибок, следующий без верных."""
    stats = _level_stats(session)
    i = level_index(mc_level)
    own = stats.get(mc_level) if mc_level != Level.A0 else None
    above = stats.get(LEVEL_ORDER[i + 1]) if i + 1 < len(LEVEL_ORDER) else None
    clean_own = own is None or own[0] == own[1]
    clean_above = above is None or above[1] == 0
    return TestSession.Confidence.HIGH if clean_own and clean_above else TestSession.Confidence.MEDIUM


def _finish(session: TestSession, *, final_level: str, confidence: str, needs_review: bool) -> TestSession:
    session.final_level = final_level
    session.confidence = confidence
    session.needs_review = needs_review
    session.status = TestSession.Status.COMPLETED
    session.current_question = None
    session.finished_at = timezone.now()
    session.save()

    lead = session.lead
    lead.assessed_level = final_level
    lead.status = Lead.Status.NEEDS_MANAGER if needs_review else Lead.Status.TESTED
    lead.save(update_fields=["assessed_level", "status", "updated_at"])
    return session


def _advance(session: TestSession) -> Step:
    kind, level = _next_step(session)
    if kind == "ask":
        asked_ids = session.answers.values_list("question_id", flat=True)
        candidates = list(Question.objects.filter(level=level, is_active=True).exclude(id__in=asked_ids))
        if candidates:
            question = random.choice(candidates)
            session.current_question = question
            session.save(update_fields=["current_question"])
            return NextQuestion(question=question, number=session.answers.count() + 1)
        # Вопросы уровня закончились, а решения нет — считаем уровень несданным.
        kind, level = "done", LEVEL_ORDER[level_index(level) - 1]

    session.mc_level = level
    session.current_question = None
    task = None
    if level_index(level) >= level_index(WRITING_FROM_LEVEL):
        task = WritingTask.objects.filter(level=level, is_active=True).order_by("?").first()
    if task:
        session.status = TestSession.Status.WRITING
        session.writing_task = task
        session.save(update_fields=["mc_level", "current_question", "status", "writing_task"])
        return NeedWriting(task=task)

    session.save(update_fields=["mc_level", "current_question"])
    return Finished(_finish(session, final_level=level, confidence=_mc_confidence(session, level), needs_review=False))


@transaction.atomic
def start_test(lead: Lead, declared_level: str = "") -> Step:
    """Начать новый тест. Незавершённые прежние попытки помечаются брошенными."""
    if not Question.objects.filter(is_active=True).exists():
        raise NoQuestions("Банк вопросов пуст: запустите seed_assessment или добавьте вопросы в админке.")
    TestSession.objects.filter(
        lead=lead, status__in=[TestSession.Status.IN_PROGRESS, TestSession.Status.WRITING]
    ).update(status=TestSession.Status.ABANDONED)
    declared = declared_level or lead.declared_level
    session = TestSession.objects.create(center=lead.center, lead=lead, declared_level=declared)
    return _advance(session)


def active_session(lead: Lead) -> TestSession | None:
    return (
        TestSession.objects.filter(lead=lead, status__in=[TestSession.Status.IN_PROGRESS, TestSession.Status.WRITING])
        .select_related("writing_task")
        .first()
    )


def last_completed_session(lead: Lead) -> TestSession | None:
    return TestSession.objects.filter(lead=lead, status=TestSession.Status.COMPLETED).first()


@transaction.atomic
def submit_answer(session: TestSession, *, question_id: int, option: int) -> Step:
    session = TestSession.objects.select_for_update(of=("self",)).select_related("current_question", "lead").get(pk=session.pk)
    if session.status != TestSession.Status.IN_PROGRESS:
        raise InvalidState("Тест уже не принимает ответы.")
    question = session.current_question
    if question is None or question.id != question_id:
        raise WrongQuestion("Это не текущий вопрос теста.")
    if not 0 <= option < len(question.options):
        raise WrongQuestion("Такого варианта нет.")
    TestAnswer.objects.create(
        session=session, question=question, chosen_option=option, is_correct=option == question.correct_option
    )
    return _advance(session)


def word_count(text: str) -> int:
    return len(text.split())


@transaction.atomic
def save_writing(session: TestSession, text: str) -> TestSession:
    """Сохранить письменный ответ до оценки ИИ."""
    session = TestSession.objects.select_for_update(of=("self",)).select_related("writing_task").get(pk=session.pk)
    if session.status != TestSession.Status.WRITING:
        raise InvalidState("Сейчас письменный ответ не ожидается.")
    words = word_count(text)
    if words < session.writing_task.min_words:
        raise WritingTooShort(words, session.writing_task.min_words)
    session.writing_text = text.strip()
    session.save(update_fields=["writing_text"])
    return session


def validate_writing_assessment(level, scores, comment) -> tuple[str, dict, str]:
    if level not in TEST_LEVELS and level != Level.A0:
        raise InvalidWritingAssessment(f"Неизвестный уровень: {level!r}")
    if not isinstance(scores, dict) or set(scores) != set(SCORE_FIELDS):
        raise InvalidWritingAssessment(f"Нужны оценки: {', '.join(SCORE_FIELDS)}")
    clean = {}
    for name in SCORE_FIELDS:
        value = scores[name]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
            raise InvalidWritingAssessment(f"Оценка {name} должна быть целым числом 1–5")
        clean[name] = value
    return level, clean, str(comment or "")[:1000]


@transaction.atomic
def submit_writing_assessment(session: TestSession, *, level: str, scores: dict, comment: str = "") -> TestSession:
    """Принять оценку письма от ИИ и вычислить итоговый уровень."""
    level, scores, comment = validate_writing_assessment(level, scores, comment)
    session = TestSession.objects.select_for_update(of=("self",)).select_related("lead").get(pk=session.pk)
    if session.status != TestSession.Status.WRITING or not session.writing_text:
        raise InvalidState("Нет письменного ответа для оценки.")

    session.writing_level = level
    session.writing_scores = scores
    session.writing_comment = comment

    diff = level_index(session.mc_level) - level_index(level)
    # Письмо не поднимает уровень выше теста: защищает от завышения (в т.ч. через текст ученика).
    final = LEVEL_ORDER[min(level_index(session.mc_level), level_index(level))]
    if diff <= 0:
        confidence, review = TestSession.Confidence.HIGH, False
    elif diff == 1:
        confidence, review = TestSession.Confidence.MEDIUM, False
    else:
        confidence, review = TestSession.Confidence.LOW, True
    return _finish(session, final_level=final, confidence=confidence, needs_review=review)


@transaction.atomic
def finish_without_writing_assessment(session: TestSession) -> TestSession:
    """ИИ недоступен: ставим уровень по тесту, письмо проверит методист."""
    session = TestSession.objects.select_for_update(of=("self",)).select_related("lead").get(pk=session.pk)
    if session.status != TestSession.Status.WRITING:
        raise InvalidState("Тест не ждёт оценки письма.")
    return _finish(session, final_level=session.mc_level, confidence=TestSession.Confidence.LOW, needs_review=True)
