FNF Chart Converter — Alpha 1.0.0
====================================

Назначение
----------
Конвертация:
- V-Slice chart JSON -> Psych Engine Mobile 1.0.4 chart JSON
- Psych Engine chart JSON -> V-Slice chart JSON + metadata JSON

Сборка Windows EXE через GitHub Actions
---------------------------------------
1. Создай новый GitHub repository.
2. Загрузи в него main.py, README_RU.txt и папку .github/workflows/build-windows.yml.
3. Открой вкладку Actions.
4. Выбери workflow "Build Windows EXE".
5. Нажми Run workflow.
6. После успешной сборки скачай artifact FNF_Chart_Converter_Windows.
7. Распакуй ZIP и запусти FNF_Chart_Converter.exe через Winlator.

Локальный запуск (если установлен Python):
    python main.py

Использование
-------------
1. Выбери JSON-файл чарта.
2. Для V-Slice выбери metadata JSON, если он есть.
3. Укажи сложность (например normal).
4. Выбери направление или оставь auto.
5. Нажми "Конвертировать".

Ограничения альфа-версии
------------------------
- Переходы BPM и границы секций восстанавливаются приближённо.
- События V-Slice и Psych пока не конвертируются; программа выводит предупреждение.
- Специальные типы нот переносятся как строка noteType, но их игровая логика может отличаться.
- Для Psych -> V-Slice исходные artist, charter, album, offsets и точная карта BPM могут быть неизвестны.
- Проверяй результат в целевой версии Psych Engine Mobile 1.0.4 на копии чарта.
- Это ранняя альфа, а не гарантия полной совместимости со всеми модифицированными сборками 1.0.4.

Форматы, на которые ориентирован конвертер:
- V-Slice chart: version / scrollSpeed / events / notes / generatedBy
- Psych chart: объект song с полями song / notes / bpm / speed / player1 / player2 и т.д.
