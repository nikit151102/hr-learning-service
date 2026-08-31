from fastapi.routing import APIRoute


METHODS_RU = {
    "GET": "Просмотр",
    "POST": "Создание",
    "PATCH": "Обновление",
    "PUT": "Обновление",
    "DELETE": "Удаление",
}

SECTIONS_RU = {
    "health": "состояние сервиса",
    "ready": "состояние сервиса",
    "auth": "авторизация",
    "me": "текущий пользователь",
    "users": "пользователи",
    "categories": "категории",
    "materials": "материалы",
    "files": "файлы",
    "tests": "тесты",
    "questions": "вопросы",
    "answers": "ответы",
    "grades": "градации",
    "attempts": "попытки",
    "assignments": "назначения",
    "analytics": "аналитика",
}

TAGS_RU = {
    "health": "Служебные",
    "ready": "Служебные",
    "auth": "Авторизация",
    "me": "Текущий пользователь",
    "users": "Пользователи",
    "categories": "Категории",
    "materials": "Материалы",
    "files": "Файлы",
    "tests": "Тесты",
    "questions": "Тесты",
    "answers": "Тесты",
    "grades": "Тесты",
    "attempts": "Попытки",
    "assignments": "Назначения",
    "analytics": "Аналитика",
}


def apply_russian_docs(app) -> None:
    """
    Делает описания маршрутов в Swagger более понятными на русском.

    Новые роутеры уже имеют русские summary и description.
    Эта функция дополнительно русифицирует старые маршруты.
    """
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        if not route.path.startswith("/api/v1"):
            continue

        parts = [p for p in route.path.split("/") if p]
        section = parts[2] if len(parts) > 2 else "общее"

        method = next(iter(route.methods or {"GET"}))

        if not route.tags and section in TAGS_RU:
            route.tags = [TAGS_RU[section]]

        if not route.summary:
            action = METHODS_RU.get(method.upper(), "Операция")
            name = SECTIONS_RU.get(section, section)
            route.summary = f"{action}: {name}"

        if not route.description:
            route.description = route.summary