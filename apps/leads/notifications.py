from html import escape

# Текст уведомления, когда администратор отметил отказ ученика от записи.
DECLINED_TEXTS = {
    "ru": {
        "main": "Здравствуйте! Ваша запись на пробный урок{groups} отменена: при проверке администратор выяснил, что ученик сам отказался от записи.",
        "groups": " в группе «{names}»",
        "contact_phone": "Если вы отказались по ошибке или это были не вы, пожалуйста, обратитесь в администрацию по телефону {phone}.",
        "contact_center": "Если вы отказались по ошибке или это были не вы, пожалуйста, обратитесь в администрацию центра «{center}».",
    },
    "uz": {
        "main": "Assalomu alaykum! Sinov darsiga{groups} yozilishingiz bekor qilindi: administrator tekshiruvi paytida o'quvchining o'zi yozilishdan voz kechgani aniqlandi.",
        "groups": " «{names}» guruhiga",
        "contact_phone": "Agar siz adashib voz kechgan bo'lsangiz yoki bu siz bo'lmasangiz, iltimos, ma'muriyatga {phone} raqami orqali murojaat qiling.",
        "contact_center": "Agar siz adashib voz kechgan bo'lsangiz yoki bu siz bo'lmasangiz, iltimos, «{center}» o'quv markazi ma'muriyatiga murojaat qiling.",
    },
}


def declined_message(language: str, *, center_name: str, admin_phone: str, group_names: list[str]) -> str:
    texts = DECLINED_TEXTS.get(language, DECLINED_TEXTS["ru"])
    groups = texts["groups"].format(names=escape(", ".join(group_names))) if group_names else ""
    if admin_phone.strip():
        contact = texts["contact_phone"].format(phone=escape(admin_phone.strip()))
    else:
        contact = texts["contact_center"].format(center=escape(center_name))
    return f"{texts['main'].format(groups=groups)}\n\n{contact}"
