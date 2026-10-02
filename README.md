# Переход Oracle-репозитория с Windows-1251 на UTF-8

Готовый кроссплатформенный комплект для macOS, Linux и Windows. Он выполняет
одноразовую конвертацию исходного кода Oracle, настраивает локальную проверку
коммитов и позволяет запретить возвращение Windows-1251 через CI.

## Состав комплекта

```text
repository/
├── .editorconfig
├── .gitattributes
├── .githooks/
│   └── pre-commit
├── cp1251_to_utf8.py
└── tools/
    ├── setup-repository.sh
    ├── setup-repository.ps1
    └── setup-repository.cmd
```

- `cp1251_to_utf8.py` — предварительный просмотр, проверка и конвертация.
- `.githooks/pre-commit` — проверка staged-файлов непосредственно в Git index.
- `setup-repository.sh` — настройка на macOS, Linux и в Git Bash.
- `setup-repository.ps1` — настройка в Windows PowerShell 5.1+ и PowerShell 7+.
- `setup-repository.cmd` — удобный Windows-запускатель, самостоятельно выбирающий
  `pwsh.exe` или `powershell.exe`.
- `.editorconfig` — указание редакторам сохранять Oracle-файлы в UTF-8.
- `.gitattributes` — LF для Git hook и shell-скрипта, CRLF для Windows-скриптов.

## Требования

- Git.
- Python 3.9 или новее.
- На Windows рекомендуется Git for Windows. Он содержит shell, которым Git
  запускает `pre-commit`.
- Для установки на Windows подходит встроенный Windows PowerShell 5.1 либо
  PowerShell 7.

Скрипты ищут Python в следующем порядке:

- POSIX/Git hook: `python3`, затем `py -3`, затем `python`;
- PowerShell: `py -3`, затем `python3`, затем `python`.

Каждый найденный вариант проверяется на версию Python 3.9+, поэтому случайный
Python 2 не будет использован.

## Добавление комплекта в репозиторий

Скопируйте содержимое каталога `oracle-cp1251-to-utf8` в корень целевого
Git-репозитория. Каталог `tests` переносить необязательно.

На macOS/Linux зафиксируйте executable-bit:

```bash
chmod +x .githooks/pre-commit
chmod +x cp1251_to_utf8.py
chmod +x tools/setup-repository.sh

git add \
  .editorconfig \
  .gitattributes \
  .githooks/pre-commit \
  cp1251_to_utf8.py \
  tools/setup-repository.sh \
  tools/setup-repository.ps1 \
  tools/setup-repository.cmd
```

Если Git не сохранил режимы, задайте их явно:

```bash
git update-index --chmod=+x .githooks/pre-commit
git update-index --chmod=+x cp1251_to_utf8.py
git update-index --chmod=+x tools/setup-repository.sh
```

Это нужно выполнить один раз автору интеграционного коммита. Разработчикам на
Windows выполнять `chmod` не требуется: executable-bit хранится в Git index.

## Первичная настройка разработчика

### Windows: наиболее простой способ

Из `cmd.exe`:

```bat
tools\setup-repository.cmd
```

Из PowerShell:

```powershell
.\tools\setup-repository.ps1
```

Если локальная политика запрещает запуск `.ps1`, не меняйте ее глобально.
Запустите только этот файл с временным обходом политики:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass `
  -File .\tools\setup-repository.ps1
```

Либо используйте `.cmd`-запускатель — он передает тот же параметр только своему
дочернему процессу PowerShell и не изменяет политику системы.

Из Git Bash также работает общий POSIX-скрипт:

```bash
./tools/setup-repository.sh
```

### macOS и Linux

```bash
./tools/setup-repository.sh
```

Установщик выполняет локальную настройку:

```text
core.hooksPath = .githooks
```

Если у пользователя уже задан другой `core.hooksPath`, скрипт не перезаписывает
его молча, а останавливается. В этом случае hooks следует объединить вручную.

## Одноразовая конвертация репозитория

Перед началом используйте отдельную ветку и чистую рабочую директорию.

### Windows PowerShell

Предварительный просмотр:

```powershell
py -3 .\cp1251_to_utf8.py .
```

Конвертация:

```powershell
py -3 .\cp1251_to_utf8.py --apply .
```

Проверка:

```powershell
py -3 .\cp1251_to_utf8.py --check .
git diff --stat
git diff --check
git status --short
```

Если Python установлен в `PATH` без launcher, замените `py -3` на `python`:

```powershell
python .\cp1251_to_utf8.py --apply .
```

### Windows cmd.exe

```bat
py -3 cp1251_to_utf8.py .
py -3 cp1251_to_utf8.py --apply .
py -3 cp1251_to_utf8.py --check .
git diff --stat
git diff --check
```

### macOS, Linux и Git Bash

```bash
python3 cp1251_to_utf8.py .
python3 cp1251_to_utf8.py --apply .
python3 cp1251_to_utf8.py --check .
git diff --stat
git diff --check
```

Код возврата `--check`:

- `0` — выбранные файлы уже UTF-8/ASCII;
- `1` — найдены файлы Windows-1251;
- `2` — ошибка Git, файловой системы или неподдерживаемая кодировка.

После успешной конвертации создайте отдельный коммит, не содержащий изменений
логики, форматирования или переводов строк:

```bash
git add -A
git commit -m "chore: convert Oracle sources from Windows-1251 to UTF-8"
```

## Безопасное поведение конвертера

- Без `--apply` файлы не изменяются.
- По умолчанию рассматриваются только отслеживаемые Git-файлы.
- Уже корректные UTF-8 и ASCII-файлы не изменяются.
- Бинарные, отсутствующие и специальные файлы пропускаются.
- Windows-1251 декодируется строго.
- Результат записывается как UTF-8 без BOM.
- `CRLF`/`LF` и завершающий перевод строки не нормализуются.
- Запись выполняется через временный файл и атомарную замену.
- На Windows вывод не аварийно завершается из-за имени файла, которое старая
  кодовая страница консоли не умеет отобразить.

Встроенный регистронезависимый список масок:

```text
*.sql  *.ddl  *.dml  *.pks  *.pkb  *.pls  *.plsql  *.prc  *.fnc
*.trg  *.vw   *.tps  *.tpb  *.tab  *.con  *.idx    *.seq  *.syn
*.grt  *.ctl  *.spc  *.bdy  *.pkg  *.txt
```

Собственный список масок полностью заменяет встроенный:

```bash
python3 cp1251_to_utf8.py \
  --include '*.sql' \
  --include '*.migration' \
  --exclude 'vendor/*' \
  .
```

В PowerShell одиночные кавычки также защищают `*` от обработки оболочкой:

```powershell
py -3 .\cp1251_to_utf8.py `
  --include '*.sql' `
  --include '*.migration' `
  --exclude 'vendor/*' `
  .
```

Дополнительно проверить неотслеживаемые Git-файлы:

```bash
python3 cp1251_to_utf8.py --include-untracked .
```

Проверить все отслеживаемые небинарные файлы:

```bash
python3 cp1251_to_utf8.py --all-text .
```

`--all-text` следует применять только если все не-UTF-8 тексты действительно
имеют Windows-1251. Однобайтовая кодировка не имеет надежной сигнатуры, поэтому
автоматически отличить Windows-1251 от CP866 или ISO-8859-5 невозможно.

## Как работает pre-commit

Hook проверяет не рабочую директорию, а staged blobs — точные байты, которые
попадут в будущий коммит. Поэтому частичный staging не позволяет случайно
закоммитить старую Windows-1251-версию файла.

На Windows hook запускается самим Git for Windows через `sh.exe`. Пользователю
не нужно вручную открывать Git Bash. `.gitattributes` гарантирует, что hook имеет
LF и корректный shebang после checkout.

Локальный hook можно обойти через `git commit --no-verify`, поэтому CI-проверка
остается обязательной.

## CI

В pipeline для всех платформ выполняйте проверку всего checkout:

macOS/Linux runner:

```bash
python3 cp1251_to_utf8.py --check .
```

Windows runner с Python launcher:

```powershell
py -3 .\cp1251_to_utf8.py --check .
```

Windows runner с обычным Python в `PATH`:

```powershell
python .\cp1251_to_utf8.py --check .
```

Сделайте этот шаг обязательным для слияния PR/MR.

## Windows: редакторы и Oracle-клиенты

`.editorconfig` поддерживается VS Code и современными JetBrains IDE. Для другого
редактора проверьте, что сохранение явно выполняется в UTF-8, а не в системной
ANSI-кодировке Windows.

Кодировка файла и клиентская кодировка Oracle — разные настройки. После
перехода проверьте средство, фактически выполняющее миграции:

- SQLcl, SQL Developer, SQL*Plus или собственный runner должен читать UTF-8;
- Windows Terminal, консоль CI и перенаправление вывода должны корректно
  обрабатывать Unicode;
- для старых OCI/SQL*Plus-сценариев отдельно проверьте `NLS_LANG`;
- выполните тестовую миграцию с кириллицей в комментарии и строковом литерале.

Особенно опасна ситуация, когда файл уже UTF-8, а клиентское окружение продолжает
объявлять его байты как Windows-1251: в базе могут появиться искаженные строки.

## Почему не используются Git clean/smudge filters

В комплекте намеренно нет прозрачного преобразования UTF-8 ↔ Windows-1251 через
Git filters или `working-tree-encoding`. Такие решения требуют одинаковой
локальной настройки Git у каждого разработчика и усложняют IDE, diff, сборку,
CI и разрешение конфликтов.

Каноническая кодировка и в Git, и в working tree должна быть одна — UTF-8.
# cp1251-to-utf8
