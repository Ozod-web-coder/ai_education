"""Стартовый банк вопросов теста и письменных заданий.

Это заготовка для проверки работы теста. Перед пилотом банк должен проверить
и расширить методист центра (через админку).
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.assessment.models import Question, WritingTask
from apps.catalog.models import Level

# (текст, варианты, номер верного варианта)
QUESTIONS = {
    Level.A1: [
        ("I ___ a student.", ["am", "is", "are", "be"], 0),
        ("She ___ two brothers.", ["have", "has", "having", "haves"], 1),
        ("There ___ a book on the table.", ["are", "be", "is", "am"], 2),
        ("___ you like coffee?", ["Does", "Do", "Are", "Is"], 1),
        ("My birthday is ___ May.", ["on", "at", "in", "to"], 2),
    ],
    Level.A2: [
        ("Yesterday we ___ to the cinema.", ["go", "goes", "went", "gone"], 2),
        ("This bag is ___ than that one.", ["heavy", "heavier", "heaviest", "more heavy"], 1),
        ("I have lived here ___ 2019.", ["for", "since", "from", "ago"], 1),
        ("Were you at home last night? — No, I ___.", ["wasn't", "weren't", "didn't", "haven't"], 0),
        ("You ___ smoke here. It's not allowed.", ["mustn't", "don't have to", "needn't", "can"], 0),
    ],
    Level.B1: [
        ("If it rains tomorrow, we ___ at home.", ["stay", "will stay", "would stay", "stayed"], 1),
        ("The letter ___ yesterday.", ["was sent", "sent", "has sent", "is sending"], 0),
        ("I'm not used to ___ up so early.", ["get", "getting", "got", "have got"], 1),
        ("She asked me where ___.", ["I lived", "did I live", "I do live", "do I live"], 0),
        ("By the time we arrived, the film ___.",
         ["already started", "has already started", "had already started", "was already start"], 2),
    ],
    Level.B2: [
        ("If I ___ about the problem earlier, I would have helped.",
         ["knew", "had known", "have known", "would know"], 1),
        ("He denied ___ the window.", ["to break", "breaking", "break", "that he breaking"], 1),
        ("Hardly ___ the house when it started to rain.", ["I had left", "had I left", "I left", "did I leave"], 1),
        ("The project, ___ was finished last week, cost a fortune.", ["that", "which", "what", "who"], 1),
        ("You'd better ___ a doctor about that cough.", ["to see", "seeing", "see", "saw"], 2),
    ],
    Level.C1: [
        ("Not until the results were published ___ how serious the situation was.",
         ["we realised", "did we realise", "we did realise", "had realised we"], 1),
        ("She is said ___ the company before the crisis.",
         ["to leave", "to have left", "leaving", "having left"], 1),
        ("The proposal was met with ___ scepticism.",
         ["considerable", "considerate", "considering", "consideration"], 0),
        ("Had the weather been better, the match ___.",
         ["would go ahead", "would have gone ahead", "had gone ahead", "went ahead"], 1),
        ("I'd rather you ___ anyone about this.", ["don't tell", "didn't tell", "not tell", "won't tell"], 1),
    ],
}

WRITING_TASKS = [
    (Level.B1, 60,
     "Write an email to a friend about your last holiday: where you went, what you did "
     "and whether you would recommend the place."),
    (Level.B2, 100,
     "Some people think that learning online is as effective as learning in a classroom. "
     "Do you agree? Give your opinion with reasons and examples."),
    (Level.C1, 150,
     "Should universities focus on preparing students for specific jobs or on a broader education? "
     "Discuss both views and give your own opinion."),
]


class Command(BaseCommand):
    help = "Создать стартовый банк вопросов теста уровня и письменных заданий"

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        for level, items in QUESTIONS.items():
            for text, choices, correct in items:
                _, is_new = Question.objects.get_or_create(
                    text=text, defaults={"level": level, "options": choices, "correct_option": correct}
                )
                created += is_new
        for level, min_words, prompt in WRITING_TASKS:
            WritingTask.objects.get_or_create(level=level, prompt=prompt, defaults={"min_words": min_words})
        self.stdout.write(self.style.SUCCESS(
            f"Вопросов: {Question.objects.count()} (новых: {created}), "
            f"письменных заданий: {WritingTask.objects.count()}"
        ))
