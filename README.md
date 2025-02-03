# 🔄 Kaiten Migration Tool

Инструмент для миграции карточек между пространствами Kaiten с сохранением всех данных карточек, включая файлы, комментарии, чек-листы и теги.

## 🌟 Возможности

- Миграция карточек между разными пространствами Kaiten
- Перенос всех прикрепленных файлов
- Сохранение комментариев с указанием авторов
- Перенос чек-листов с сохранением статуса
- Миграция тегов с сохранением цветов
- Удобный веб-интерфейс на Streamlit
- Подробное логирование процесса миграции

## 🛠️ Технический стек

- Python 3.7+
- Streamlit
- Requests
- Kaiten API

## 📋 Требования

- Python 3.7 или выше
- Доступ к API Kaiten (токены) для обоих пространств
- ID пространств источника и назначения

## ⚙️ Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/kaiten-migration-tool.git
cd kaiten-migration-tool
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

## 🚀 Запуск

Запустите приложение с помощью Streamlit:
```bash
streamlit run main.py
```

## 📝 Использование

1. Введите данные для подключения:
   - Домены Kaiten (источник и назначение)
   - ID пространств
   - API токены

2. Нажмите "Загрузить доски" для получения списка досок

3. Выберите:
   - Исходную доску и колонку
   - Карточки для миграции
   - Целевую доску и колонку

4. Нажмите "Начать миграцию" и следите за процессом в логах

## ⚠️ Важные замечания

- Убедитесь, что у токенов есть необходимые права доступа
- Проверьте наличие свободного места для временных файлов
- Рекомендуется сначала протестировать на небольшом количестве карточек

## 🔑 Настройка токенов Kaiten

1. Перейдите в настройки профиля в Kaiten
2. Создайте новый API токен

## 👥 Поддержка

Если у вас возникли проблемы или есть предложения по улучшению:
1. Создайте Issue в репозитории
2. Опишите проблему или предложение
3. Приложите логи

## 📄 Лицензия

MIT License
