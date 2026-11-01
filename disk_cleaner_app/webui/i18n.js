/* Локализация интерфейса: русские строки разметки и скриптов → английские.
 *
 * Ключ — ровно тот текст, который стоит в элементе или строке (без крайних
 * пробелов). Статику переводит обходчик DOM, поэтому разметку править не надо;
 * строки со значениями внутри помечены tf`…` — шаблонный тег подставляет
 * английские куски, если ключ найден.
 *
 * Тексты движка (ошибки Python, отчёты, CLI) остаются русскими осознанно:
 * это не интерфейс, а данные.
 */

const UI_EN = {
  "0 Б": "0 B",
  "SMART недоступен: нужны права администратора или диск не отвечает.":
    "SMART unavailable: administrator rights required or drive not responding.",
  "owner/repo или URL манифеста": "owner/repo or manifest URL",
  "Автозапуск": "Autostart",
  "Анализ": "Analysis",
  "Анализ завершён": "Analysis finished",
  "Анализировать": "Analyze",
  "Безопасный набор": "Safe set",
  "Безопасный режим": "Safe mode",
  "Белый список путей": "Path whitelist",
  "Быстрый": "Quick",
  "В корзину": "To Recycle Bin",
  "ВС": "SUN",
  "ВТ": "TUE",
  "Версия": "Version",
  "Внешний вид и поведение": "Appearance and behavior",
  "Все диски": "All drives",
  "Все операции": "All operations",
  "Выберите отчёт выше или постройте treemap.": "Pick a report above or build a treemap.",
  "Выберите папку и запустите поиск.": "Pick a folder and start the search.",
  "Главная": "Home",
  "Глубокая очистка": "Deep clean",
  "Готов к работе": "Ready",
  "Группа": "Group",
  "Диск": "Drive",
  "Диски": "Drives",
  "Добавить": "Add",
  "Дубликатов не найдено": "No duplicates found",
  "Дубликаты": "Duplicates",
  "Журнал пуст": "Log is empty",
  "Загрузка данных…": "Loading…",
  "Закрыть": "Close",
  "Занято зря": "Wasted",
  "Занятость по дням": "Usage by day",
  "Записей автозагрузки с таким именем нет.": "No startup entry with that name.",
  "Запись": "Entry",
  "Запись в HKCU\\…\\Run, права администратора не нужны":
    "HKCU\\…\\Run entry, no administrator rights needed",
  "Запускать вместе с Windows": "Start with Windows",
  "Запускать свёрнутым в трей": "Start minimized to tray",
  "Здесь появятся операции очистки — с датой, числом целей и освобождённым местом.":
    "Cleaning operations will appear here — date, target count, freed space.",
  "Измените запрос или выберите другой диск.": "Change the query or pick another drive.",
  "Изменить": "Edit",
  "Иконка в системном трее": "System tray icon",
  "Импорт настроек": "Import settings",
  "Искать": "Search",
  "История": "History",
  "История и отчёты": "History and reports",
  "Источник": "Source",
  "Как в системе": "System",
  "Клик по папке — внутрь, кнопка «назад» — на уровень выше, двойной клик вне папки — открыть в проводнике.":
    "Click a folder to open it, Back goes up a level, double-click outside a folder to open it in Explorer.",
  "Корзина не освобождает место до своей очистки":
    "Recycle Bin frees space only after it is emptied",
  "Крупнейшие цели": "Largest targets",
  "Меню: открыть, тихая очистка, выход": "Menu: open, silent clean, exit",
  "На главной появится предложение глубокой очистки. 0 — выключить, в ГБ":
    "Home will suggest deep cleaning. 0 turns it off, in GB",
  "На уровень выше": "Up one level",
  "Нажмите «Анализировать» — приложение посчитает, сколько можно освободить.":
    "Press Analyze — the app will measure how much can be freed.",
  "Нажмите «Сканировать» — приложение посчитает, сколько можно освободить.":
    "Press Scan — the app will measure how much can be freed.",
  "Найти запись": "Find entry",
  "Найти программу": "Find program",
  "Например: D:\\Projects\\важное": "For example: D:\\Projects\\important",
  "Настройки": "Settings",
  "Нет данных о железе": "No hardware data",
  "Нечего показать": "Nothing to show",
  "Ничего не выбрано": "Nothing selected",
  "Ничего не найдено": "Nothing found",
  "Ничего не отмечено": "Nothing marked",
  "Нужны права администратора; Windows создаёт точки не чаще раза в 24 ч":
    "Administrator rights required; Windows creates points at most once per 24 h",
  "Обновить": "Refresh",
  "Объём": "Size",
  "Окно откроется только из меню иконки": "The window opens only from the tray menu",
  "Операция": "Operation",
  "Освобождено": "Freed",
  "Освобождено по дням": "Freed by day",
  "Остановить": "Stop",
  "Открыть лог": "Open log",
  "Отметьте цели или возьмите безопасный набор": "Mark targets or take the safe set",
  "Очистить": "Clean",
  "Очистить историю": "Clear history",
  "Очистка": "Cleanup",
  "Очисток выполнено": "Cleanups done",
  "Очищено всего": "Freed in total",
  "ПН": "MON",
  "ПТ": "FRI",
  "Папка данных": "Data folder",
  "Папка…": "Folder…",
  "Перезапустить с правами администратора": "Restart as administrator",
  "Перемещать удалённое в корзину": "Move deleted files to Recycle Bin",
  "Поиск целей": "Target search",
  "Пока ничего не найдено": "Nothing found yet",
  "Показать план": "Show plan",
  "Показывать и выбирать только безопасные цели": "Show and pick only safe targets",
  "Пользовательские правила": "Custom rules",
  "Порог свободного места для баннера": "Free space threshold for the banner",
  "Предпросмотр": "Preview",
  "Применяется сразу": "Applied immediately",
  "Проверить обновления": "Check for updates",
  "Программа": "Program",
  "Простая": "Easy",
  "Пустые папки": "Empty folders",
  "Развернуть": "Expand",
  "Раздел ещё в старом интерфейсе": "This section still uses the old interface",
  "Размер": "Size",
  "Расписание очистки": "Cleanup schedule",
  "Распределение по слоям": "Distribution by layer",
  "Расширенная": "Advanced",
  "Резервная копия и обновления": "Backup and updates",
  "СБ": "SAT",
  "СР": "WED",
  "Сброс": "Reset",
  "Свернуть": "Collapse",
  "Светлая": "Light",
  "Свободно на диске": "Free on disk",
  "Системные каталоги и личные папки целиком добавить нельзя.":
    "System folders and personal folders cannot be added whole.",
  "Сканировать": "Scan",
  "Скачать и установить": "Download and install",
  "Снять выбор": "Clear selection",
  "Содержимое перезаписывается нулями перед удалением: файлы не восстановить, корзина не используется. Заметно медленнее и изнашивает SSD":
    "Contents are overwritten with zeros before deletion: files cannot be recovered, the Recycle Bin is not used. Noticeably slower and wears out SSDs",
  "Создать задание": "Create task",
  "Состояние": "Status",
  "Состояние системы и быстрые действия": "System status and quick actions",
  "Стирать удалённое безвозвратно": "Shred deleted files",
  "Стоп": "Stop",
  "Тема оформления": "Theme",
  "Температура": "Temperature",
  "Топ папок": "Top folders",
  "Точка восстановления перед глубокой очисткой": "Restore point before deep cleaning",
  "Точный": "Exact",
  "Тёмная": "Dark",
  "Удалить": "Delete",
  "Удалить задание": "Delete task",
  "Удалить копии": "Delete copies",
  "Удалить пустые": "Delete empty",
  "Удалённое сначала попадает в корзину": "Deleted files go to the Recycle Bin first",
  "Установлена": "Installed",
  "Файлы и фильтры": "Files and filters",
  "Цель": "Target",
  "ЧТ": "THU",
  "Экспорт CSV": "Export CSV",
  "Экспорт JSON": "Export JSON",
  "Экспорт настроек": "Export settings",
  "Этот экран пока открывается в Tk-версии приложения — новые страницы появляются по одной.":
    "This screen still opens in the Tk build — pages are being ported one by one.",
  "Язык интерфейса": "Interface language",
  "Масштаб интерфейса": "Interface scale",
  "включено": "on",
  "журнал пуст": "log is empty",
  "занято": "used",
  "не запускали": "never run",
  "не искали": "not searched",
  "не проанализировано": "not analyzed",
  "операций": "operations",
  "освобождено": "freed",
  "отключено": "off",
  "программ": "programs",
  "размеры считаются…": "sizes are being counted…",
  "томов": "volumes",
  "фильтр": "filter",
  "читаем SMART…": "reading SMART…",
  "читаем реестр…": "reading registry…",
  // ── строки из app.js ────────────────────────────────
  "Анализ завершён: найдено": "Analysis finished: found",
  "Безопасное сканирование и удаление временных данных":
    "Safe scan and removal of temporary data",
  "Готов к работе · ": "Ready · ",
  "Задание не создано.": "No task created.",
  "Занятость томов, прогноз и состояние железа":
    "Volume usage, forecast and hardware status",
  "Запрашиваю UAC…": "Requesting UAC…",
  "Измените запрос или снимите фильтр слоя.": "Change the query or clear the layer filter.",
  "Изменить правило": "Edit rule",
  "Каждый слой — отдельный уровень риска. Сначала анализ, потом очистка.":
    "Each layer is its own risk level. Analyze first, then clean.",
  "Крестик прячет окно в трей; меню: открыть, тихая очистка, выход":
    "The close button hides the window to the tray; menu: open, silent clean, exit",
  "Крупные папки, файлы, расширения и treemap":
    "Large folders, files, extensions and treemap",
  "Не удалось загрузить движок: ": "Failed to load the engine: ",
  "Недоступно: трей не установлен": "Unavailable: tray is not installed",
  "Ничего не подходит под фильтр": "Nothing matches the filter",
  "Новое правило": "New rule",
  "Одинаковые файлы: покажем и удалим лишние копии":
    "Identical files: we will show and delete extra copies",
  "Отмена": "Cancel",
  "Очистка…": "Cleaning…",
  "Перезапустить": "Restart",
  "План очистки": "Cleanup plan",
  "Программы": "Programs",
  "Прочее": "Other",
  "Размеры посчитаны": "Sizes counted",
  "Строим план…": "Building the plan…",
  "Тема, правила, история, расписание и обновления":
    "Theme, rules, history, schedule and updates",
  "Установленные приложения, их размер и удаление":
    "Installed apps, their size and removal",
  "Что запускается вместе с Windows": "What starts with Windows",
  "Что и когда удалялось": "What was deleted and when",
  "Экспорт не удался": "Export failed",
  "без прав администратора": "without administrator rights",
  "идёт поиск…": "searching…",
  "ничего не найдено": "nothing found",
  "права администратора": "administrator rights",
  "Правил пока нет.": "No rules yet.",
  "Список пуст — эти пути никогда не попадут в план очистки.":
    "The list is empty — these paths never get into a cleanup plan.",
  "Безопасно": "Safe",
  "Осторожно": "Careful",
  "Продвинутый": "Advanced",
  "Название": "Name",
  "Путь (папка или файл)": "Path (folder or file)",
  "Уровень риска": "Risk level",
  "Сохранить": "Save",
  "Путь будет проверен правилами безопасности перед добавлением.":
    "The path is checked by the safety rules before it is added.",
  "Правило не сохранено": "Rule not saved",
  "Удалить правило?": "Delete the rule?",
  "без прав администратора": "no administrator rights",
  "Занято \u0001 из \u0001 · свободно \u0001%": "Used \u0001 of \u0001 · \u0001% free",
  "занято \u0001 из \u0001 · \u0001%": "used \u0001 of \u0001 · \u0001%",
  "найдено \u0001 · целей \u0001 из \u0001": "found \u0001 · targets \u0001 of \u0001",
  "\u0001 цел.": "\u0001 tgt.",
  "\u0001 целей · \u0001 проанализировано": "\u0001 targets · \u0001 scanned",
  "«\u0001» пока в Tk-версии": "\u0001 still opens in the Tk build",
  "\u0001 → \u0001 · точек \u0001": "\u0001 → \u0001 · points \u0001",
  "Автозагрузка: \u0001 включено, \u0001 отключено": "Startup: \u0001 on, \u0001 off",
  "Программ: \u0001": "Programs: \u0001",
  "\u0001 из \u0001": "\u0001 of \u0001",
  "нужны права": "admin rights needed",
  "Диск: \u0001": "Drive: \u0001",
  "Удаление: \u0001…": "Uninstalling \u0001…",
  "SMART прочитан: дисков \u0001": "SMART read: \u0001 disks",
  "Удалено пустых папок: \u0001": "Empty folders deleted: \u0001",
  "Treemap: \u0001 элементов": "Treemap: \u0001 elements",
  "\u0001 записей": "\u0001 entries",
  "выбрано \u0001 · ": "selected \u0001 · ",
  "Прогноз появится, когда накопится история: нужно ≥ 4 точек за ≥ 7 дней наблюдений.":
    "The forecast appears once there is history: at least 4 points over 7+ days.",
  "Русский": "Russian",
  "Автозагрузка": "Startup",
  "Безопасные": "Safe",
  "Требуют внимания": "Needs attention",
  "Опасные": "Risky",
  "Раздел": "Section",
  "Экран ещё не перенесён на новый интерфейс": "This screen is not ported to the new interface yet",
  "«\u0001» пока в Tk-версии": "\u0001 still lives in the Tk build",
  "Точки появляются после очисток и запусков — нужно хотя бы две.": "Points appear after cleanups and scans — at least two are needed.",
  "Занято \u0001 из \u0001 · свободно \u0001%": "Used \u0001 of \u0001 · \u0001% free",
  "Нет данных о диске": "No disk data",
  "\u0001 → \u0001 · точек \u0001": "\u0001 → \u0001 · points \u0001",
  "нет данных": "no data",
  "Пока нет данных": "No data yet",
  "Запустите анализ — здесь появятся самые крупные цели.": "Run an analysis — the largest targets will show up here.",
  "Не удалось прочитать состояние диска:": "Could not read disk state:",
  "Диск \u0001": "Drive \u0001",
  "Нет данных — журнал пока пуст.": "No data — the log is empty so far.",
  "\u0001 из \u0001": "\u0001 of \u0001",
  "\u0001 цел.": "\u0001 targets",
  "Не удалось прочитать историю:": "Could not read history:",
  "готово": "done",
  "Удалить программу": "Uninstall program",
  "Читаю установленные программы…": "Reading installed programs…",
  "Программ: \u0001": "Programs: \u0001",
  "Не удалось прочитать список программ:": "Could not read the program list:",
  "\u0001 записей": "\u0001 entries",
  "Автозагрузка: \u0001 включено, \u0001 отключено": "Startup: \u0001 on, \u0001 off",
  "Не удалось прочитать автозагрузку:": "Could not read startup entries:",
  "Включаю запись…": "Enabling entry…",
  "Отключаю запись…": "Disabling entry…",
  "Запись включена": "Entry enabled",
  "Запись отключена": "Entry disabled",
  "Отмечено \u0001 файлов · \u0001": "Marked \u0001 files · \u0001",
  "\u0001 групп · \u0001": "\u0001 groups · \u0001",
  "Путь защищён белым списком": "Path is protected by the allow list",
  "\u0001 файлов · \u0001": "\u0001 files · \u0001",
  "Ищем дубликаты…": "Searching for duplicates…",
  "Удалить копии?": "Delete copies?",
  "Будет удалено файлов: ": "Files to delete: ",
  ". Оригинал в каждой группе остаётся на месте.": ". The original in each group stays in place.",
  "Удаляем копии…": "Deleting copies…",
  "свободно": "free",
  "занято \u0001 из \u0001 · \u0001%": "used \u0001 of \u0001 · \u0001%",
  "\u0001 дисков": "\u0001 drives",
  "Диск: \u0001": "Drive: \u0001",
  "анализ…": "analysis…",
  "Изменён": "Modified",
  "Путь": "Path",
  "подходит \u0001 · \u0001": "matches \u0001 · \u0001",
  "остановлено": "stopped",
  "кэш \u0001 · «Обновить» для повтора": "cached \u0001 · press Refresh to retry",
  "пустых папок: \u0001": "empty folders: \u0001",
  "\u0001 папок": "\u0001 folders",
  "Папка": "Folder",
  "Расположение": "Location",
  "Пустые папки: \u0001": "Empty folders: \u0001",
  "\u0001 элементов": "\u0001 items",
  "Отчёт сохранён: \u0001": "Report saved: \u0001",
  "✅ Задание активно: \u0001, раз в неделю.": "✅ Task active: \u0001, once a week.",
  "Операций: \u0001 · освобождено всего: \u0001": "Operations: \u0001 · freed in total: \u0001",
  "• \u0001 — \u0001 целей, \u0001": "• \u0001 — \u0001 targets, \u0001",
  "Правило изменено": "Rule updated",
  "Правило добавлено": "Rule added",
  "Удалить программу?": "Uninstall the program?",
  "Запустится штатный деинсталлятор Windows — возможно, с вопросом на экране. Остатки и папки настроек он не трогает.": "The standard Windows uninstaller starts — it may ask a question on screen. It does not touch leftovers or settings folders.",
  "Удаление: \u0001…": "Uninstalling: \u0001…",
  "всего \u0001": "\u0001 total",
  "<span class=\"tag err\">недоступно</span>": "<span class=\"tag err\">unavailable</span>",
  "<span class=\"tag warn\">нужны права</span>": "<span class=\"tag warn\">admin required</span>",
  "<span class=\"tag\">не проанализировано</span>": "<span class=\"tag\">not scanned</span>",
  "Выбрано \u0001 · \u0001": "Selected \u0001 · \u0001",
  "Проверьте план перед удалением": "Check the plan before deleting",
  "найдено \u0001 · целей \u0001 из \u0001": "found \u0001 · targets \u0001 of \u0001",
  "не проанализировано · целей \u0001": "not scanned · targets \u0001",
  "\u0001 целей · \u0001 проанализировано": "\u0001 targets · \u0001 scanned",
  " · ошибок \u0001": " · \u0001 errors",
  "Отметьте цель с предпросмотром — покажем первые файлы внутри.": "Tick a target with the preview — the first files inside will be shown.",
  "Папка пуста или недоступна": "Folder is empty or unavailable",
  "Показаны первые \u0001 элементов — удаляется содержимое целиком.": "Showing the first \u0001 items — the whole content is deleted.",
  "Предпросмотр: \u0001": "Preview: \u0001",
  "Анализ целей…": "Scanning targets…",
  "Остановлено": "Stopped",
  "будет освобождено": "will be freed",
  "действий: ": "actions: ",
  "Что будет удалено": "What will be deleted",
  "(только показ)": "(preview only)",
  "Без прав администратора будет пропущено целей: \u0001.": "Without administrator rights \u0001 targets will be skipped.",
  "Удалённое попадёт в корзину — место освободится после её очистки.": "Deleted items go to the Recycle Bin — space frees up after it is emptied.",
  "Анализ целей… \u0001 из \u0001": "Scanning targets… \u0001 of \u0001",
  "Анализ завершён: найдено \u0001": "Scan finished: found \u0001",
  "Анализ завершён: найдено \u0001 · выбран безопасный набор": "Scan finished: found \u0001 · safe set selected",
  "План готов: \u0001, действий \u0001": "Plan ready: \u0001, \u0001 actions",
  "Очистка… \u0001 из \u0001": "Cleaning… \u0001 of \u0001",
  "Очистка завершена за \u0001 с · освобождено \u0001": "Cleanup finished in \u0001 s · freed \u0001",
  "Очистка завершена": "Cleanup finished",
  "Освобождено \u0001": "Freed \u0001",
  "за \u0001 с": "in \u0001 s",
  "Готово": "Done",
  "проверено \u0001": "\u0001 checked",
  "Найдено групп: \u0001 · зря занято \u0001": "Groups found: \u0001 · wasted \u0001",
  "SMART прочитан: дисков \u0001": "SMART read: \u0001 drives",
  "Анализ остановлен": "Scan stopped",
  "Удалено пустых папок: \u0001": "Empty folders removed: \u0001",
  "Часть папок не удалена": "Some folders were not removed",
  "Понятно": "Got it",
  "Treemap: \u0001 элементов": "Treemap: \u0001 items",
  "Не удалось получить права администратора": "Could not obtain administrator rights",
  "Страница: \u0001": "Page: \u0001",
  "Удалено файлов: \u0001 · освобождено \u0001": "Files deleted: \u0001 · freed \u0001",
  "Удалено с ошибками": "Deleted with errors",
  "Копии удалены": "Copies deleted",
  "Удалено: ": "Deleted: ",
  "Деинсталлятор запущен": "Uninstaller started",
  "Не удалось запустить удаление": "Could not start uninstall",
  "Удаление запущено": "Uninstall started",
  "Удаление невозможно": "Uninstall is not possible",
  "Поиск остановлен": "Search stopped",
  "Права администратора": "Administrator rights",
  "Перезапустить приложение с правами администратора? Нужны они для системных целей глубокой очистки, SMART-атрибутов и VSS. Текущее окно закроется.": "Restart the app with administrator rights? They are needed for system deep-clean targets, SMART attributes and VSS. The current window will close.",
  "останавливаем…": "stopping…",
  "Удалить пустые папки?": "Delete empty folders?",
  "Удаляются только папки без файлов и подпапок, корень сканирования защищён.": "Only folders without files and subfolders are removed; the scan root is protected.",
  "удаляем…": "deleting…",
  "Тема не сохранена": "Theme not saved",
  "Тема применена": "Theme applied",
  "Не сохранено": "Not saved",
  "Сохранено": "Saved",
  "Порог не сохранён": "Threshold not saved",
  "Порог сохранён": "Threshold saved",
  "Автозапуск не изменён": "Autostart unchanged",
  "Автозапуск обновлён": "Autostart updated",
  "Не удалось открыть лог": "Could not open the log",
  "Очистка истории": "Clear history",
  "Не удалось очистить": "Could not clear",
  "История очищена": "History cleared",
  "Выберите правило в списке": "Pick a rule in the list",
  "Удаление правила": "Delete rule",
  "Удалить правило «\u0001»?": "Delete the rule \u0001?",
  "Файлы на диске не удаляются — правило исчезнет из списка целей.": "Files on disk are not deleted — the rule disappears from the target list.",
  "Не удалось удалить": "Could not delete",
  "Правило удалено": "Rule deleted",
  "Путь не добавлен": "Path not added",
  "Путь добавлен в белый список": "Path added to the allow list",
  "Выберите путь в списке": "Pick a path in the list",
  "Путь убран из белого списка": "Path removed from the allow list",
  "Не удалось создать задание": "Could not create the task",
  "Задание создано": "Task created",
  "Не удалось удалить задание": "Could not delete the task",
  "Задание удалено": "Task deleted",
  "Настройки экспортированы: \u0001": "Settings exported: \u0001",
  "Импорт не удался": "Import failed",
  "Источник не сохранён": "Source not saved",
  "Источник обновлений сохранён": "Update source saved",
  "Проверяю обновления…": "Checking for updates…",
  "Скачиваю обновление…": "Downloading the update…",
  "Скачиваю и устанавливаю обновление — приложение перезапустится": "Downloading and installing the update — the app will restart",
  "Удалённое будет перемещено в корзину": "Deleted items go to the Recycle Bin",
  "Удаление без корзины": "Delete permanently",
  "Готов к работе · \u0001": "Ready · \u0001",
  "Не удалось загрузить движок: \u0001": "Could not load the engine: \u0001",
  "Настроек применено: ": "Settings applied: ",
  "· правил добавлено: ": "· rules added: ",
};

/* Куски строк, которые попадают в DOM вместе со значениями:
   «12 файлов · 3 ГБ». Заменяем только целые слова. */
const UI_FRAG = [
  [/(?<![\p{L}])файлов(?![\p{L}])/gu, "files"],
  [/(?<![\p{L}])записей(?![\p{L}])/gu, "entries"],
  [/(?<![\p{L}])групп(?![\p{L}])/gu, "groups"],
  [/(?<![\p{L}])элементов(?![\p{L}])/gu, "elements"],
  [/(?<![\p{L}])зря занято(?![\p{L}])/gu, "wasted"],
  [/(?<![\p{L}])выбрано(?![\p{L}])/gu, "selected"],
  [/(?<![\p{L}])освобождено(?![\p{L}])/gu, "freed"],
  // Размеры приходят из Python уже строкой («12.6 ГБ») — переводим единицы.
  [/(\d)\s*ТБ(?![\p{L}])/gu, "$1 TB"],
  [/(\d)\s*ГБ(?![\p{L}])/gu, "$1 GB"],
  [/(\d)\s*МБ(?![\p{L}])/gu, "$1 MB"],
  [/(\d)\s*КБ(?![\p{L}])/gu, "$1 KB"],
  [/(\d)\s*Б(?![\p{L}])/gu, "$1 B"],
];

const UI_LANG_DEFAULT = "ru";
let UI_LANG = UI_LANG_DEFAULT;
const UI_ORIG = new WeakMap();

/* Целые фразы со значениями внутри: ключ — шаблон с разделителем \u0001.
   tf`Очистка завершена за ${s} с` */
const UI_TPL = {
  "Очистка завершена за \u0001 с · освобождено \u0001": "Cleanup finished in \u0001 s · freed \u0001",
  "Очистка… \u0001 из \u0001": "Cleaning… \u0001 of \u0001",
  "Анализ целей… \u0001 из \u0001": "Analyzing targets… \u0001 of \u0001",
  "Анализ завершён: найдено \u0001": "Analysis finished: found \u0001",
  "Анализ завершён: найдено \u0001 · выбран безопасный набор":
    "Analysis finished: found \u0001 · safe set selected",
  "План готов: \u0001, действий \u0001": "Plan ready: \u0001, \u0001 actions",
  "Удалено файлов: \u0001 · освобождено \u0001": "Files deleted: \u0001 · freed \u0001",
  "Найдено групп: \u0001 · зря занято \u0001": "Groups found: \u0001 · wasted \u0001",
  "Отмечено \u0001 файлов · \u0001": "Marked \u0001 files · \u0001",
  "Операций: \u0001 · освобождено всего: \u0001\n": "Operations: \u0001 · freed in total: \u0001\n",
  "• \u0001 — \u0001 целей, \u0001": "• \u0001 — \u0001 targets, \u0001",
  "✅ Задание активно: \u0001, раз в неделю.": "✅ Task is active: \u0001, weekly.",
  "Отчёт сохранён: \u0001": "Report saved: \u0001",
  "Диск \u0001": "Drive \u0001",
  "Готов к работе · \u0001": "Ready · \u0001",
};

/* Шаблонный тег для строк со значениями. */
function tf(parts, ...values) {
  const key = parts.join("\u0001");
  // Шаблон со значениями ищется и в UI_TPL, и в общем словаре: шаблон
  // «Занято \u0001 из \u0001» лежит там же, где обычные строки.
  const table = UI_TPL[key] !== undefined ? UI_TPL : UI_EN;
  const text = UI_LANG === "en" && table[key] !== undefined ? table[key] : key;
  return text
    .split("\u0001")
    .reduce((acc, part, index) => acc + part + (index < values.length ? values[index] : ""), "");
}

/* Точный перевод одного значения (для подстановок внутрь tf). */
function t(text) {
  const key = String(text ?? "").trim();
  if (UI_LANG !== "en") return text;
  return UI_EN[key] !== undefined ? UI_EN[key] : text;
}

function translate(text) {
  if (UI_LANG !== "en") return text;
  const key = text.trim();
  if (key && UI_EN[key] !== undefined) return text.replace(key, UI_EN[key]);
  // Текст, разбитый в разметке на строки: пробельные серии сравниваем как одну.
  const flat = key.replace(/\s+/g, " ");
  if (key && flat !== key && UI_EN[flat] !== undefined) {
    return text.replace(key, UI_EN[flat]);
  }
  // Подпись с иконкой впереди («✕ без прав администратора»): иконку не трогаем.
  // \p{L} с флагом u — иначе \W съедает и кириллицу.
  const bare = key.replace(/^[^\p{L}\p{N}]+/u, "");
  if (bare && bare !== key && UI_EN[bare] !== undefined) {
    return text.replace(bare, UI_EN[bare]);
  }
  let out = text;
  for (const [pattern, value] of UI_FRAG) out = out.replace(pattern, value);
  return out;
}

const SKIP_TAGS = new Set(["SCRIPT", "STYLE"]);

function translateElement(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    if (!UI_ORIG.has(node)) UI_ORIG.set(node, node.nodeValue);
    const raw = UI_ORIG.get(node);
    const next = translate(raw);
    if (node.nodeValue !== next) node.nodeValue = next;
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE || SKIP_TAGS.has(node.tagName)) return;
  for (const attr of ["placeholder", "title", "aria-label"]) {
    if (!node.hasAttribute(attr)) continue;
    const store = `data-ru-${attr}`;
    if (!node.hasAttribute(store)) node.setAttribute(store, node.getAttribute(attr));
    const raw = node.getAttribute(store);
    const next = translate(raw);
    if (node.getAttribute(attr) !== next) node.setAttribute(attr, next);
  }
}

function translateTree(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
  let node = root;
  translateElement(node);
  while ((node = walker.nextNode())) translateElement(node);
}

/* Переводим и то, что интерфейс дорисовывает после загрузки. */
function watchDynamicText() {
  const observer = new MutationObserver((records) => {
    for (const record of records) {
      if (record.type === "characterData") translateElement(record.target);
      for (const node of record.addedNodes) {
        if (node.nodeType === Node.TEXT_NODE) translateElement(node);
        else if (node.nodeType === Node.ELEMENT_NODE) translateTree(node);
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, characterData: true });
}

function applyUi(settings) {
  UI_LANG = settings && settings.ui_lang === "en" ? "en" : "ru";
  document.documentElement.lang = UI_LANG;
  const scale = Number(settings && settings.ui_scale) || 100;
  document.body.style.zoom = `${Math.min(150, Math.max(100, scale))}%`;
  translateTree(document.body);
}
