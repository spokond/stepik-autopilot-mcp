# Stepik Autopilot MCP

Локальный MCP-сервер, который позволяет AI-агенту получать практические задания
Stepik, решать их пакетами, отправлять ответы и сохранять состояние прохождения в
SQLite.

Сервер не содержит собственной модели и не требует API-ключ OpenAI или
Anthropic. Задания решает модель MCP-клиента: Codex, Claude Code или Pi.

> [!WARNING]
> Ответы действительно отправляются в ваш аккаунт Stepik и могут расходовать
> доступные попытки. Сначала используйте `stepik_plan`, а для проверки ответов —
> режим `review` и `action="save"`.

## Текущие возможности и ограничения

- Поддерживаются `choice` (одиночный и множественный выбор), `string`, `number`,
  `sql` и `code`. Численные ответы передаются строкой без потери точности; для `code`
  язык должен быть одним из языков конкретной попытки.
- Блоки `text` и `video` исключаются из обычного запуска. Сервер не создаёт для
  них попытки, не отмечает их просмотренными и не загружает видео.
- Остальные практические типы показываются как `unsupported` и
  не отправляются, пока для них не будет подтверждён отдельный контракт reply.
- Состояние запусков, пакетов и отправок хранится в локальной SQLite-базе. После
  перезапуска клиента незавершённый запуск можно продолжить.
- MCP-сервер управляет Stepik API и состоянием, но не работает автономно:
  клиентский агент должен оставаться активным, чтобы решать следующие пакеты.

## 1. Что потребуется

- аккаунт Stepik с подтверждённой почтой;
- доступ к нужному курсу из этого аккаунта;
- Git;
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/);
- один из клиентов: [Codex CLI](https://developers.openai.com/codex/cli),
  [Claude Code](https://code.claude.com/docs/en/quickstart) или
  [Pi coding agent](https://pi.dev/).

Проект требует Python 3.14 или новее. Обычно `uv` сам установит подходящую
версию Python при синхронизации проекта.

Проверьте основные команды:

```sh
git --version
uv --version
```

## 2. Скачать и установить

```sh
git clone https://github.com/spokond/stepik-autopilot-mcp.git
cd stepik-autopilot-mcp
uv sync --locked --all-groups
```

Если проект уже скачан, выполняйте дальнейшие команды из его корня — каталога,
где находятся `pyproject.toml` и `.env.example`.

Запомните два абсолютных пути: они понадобятся при настройке MCP-клиента.

```sh
pwd
command -v uv
```

Например:

```text
/Users/me/projects/stepik-autopilot-mcp
/Users/me/.local/bin/uv
```

Далее в примерах:

- `/ABS/PATH/TO/stepik-autopilot-mcp` — результат `pwd`;
- `/ABS/PATH/TO/uv` — результат `command -v uv`.

Не оставляйте эти шаблоны без замены.

## 3. Создать OAuth-приложение Stepik

1. Войдите в тот аккаунт Stepik, прогресс которого хотите использовать.
2. Откройте [страницу OAuth-приложений](https://stepik.org/oauth2/applications/).
3. Создайте новое приложение.
4. Выберите тип клиента **Confidential** и тип авторизации
   **Client credentials**. Redirect URI для этого режима не используется.
5. Сохраните приложение.
6. Скопируйте выданные `Client ID` и `Client secret`.

Сервер использует OAuth 2 Client Credentials и получает временный access token
самостоятельно. Логин и пароль Stepik в `.env` вводить не нужно. Описание этого
режима есть в [официальной справке Stepik API](https://help.stepik.org/article/64188).

> [!CAUTION]
> `Client secret` даёт доступ от имени вашего приложения. Не публикуйте его, не
> вставляйте в сообщения агенту и не добавляйте `.env` в Git.

## 4. Настроить `.env`

Создайте локальный файл из примера:

```sh
cp .env.example .env
```

Откройте `.env` в редакторе и замените только два значения-заглушки:

```dotenv
STEPIK__BASE_URL=https://stepik.org

STEPIK__OAUTH__CLIENT_ID=вставьте-client-id
STEPIK__OAUTH__CLIENT_SECRET=вставьте-client-secret
```

Что означает каждая настройка:

| Переменная | Нужно менять | Назначение |
|---|---:|---|
| `STEPIK__BASE_URL` | нет | Адрес Stepik. Для обычной установки оставьте `https://stepik.org`. |
| `STEPIK__OAUTH__CLIENT_ID` | да | `Client ID` созданного OAuth-приложения. |
| `STEPIK__OAUTH__CLIENT_SECRET` | да | `Client secret` созданного OAuth-приложения. |

Есть дополнительные необязательные настройки. Их не нужно добавлять, если нет
конкретной причины менять лимиты:

```dotenv
STEPIK__REQUESTS_PER_SECOND=5
STEPIK__REQUEST_BURST=10
STEPIK__MAX_IN_FLIGHT=4
```

Допустимые значения задаются проектом:

- `REQUESTS_PER_SECOND`: больше `0`, не больше `100`;
- `REQUEST_BURST`: от `1` до `100`;
- `MAX_IN_FLIGHT`: от `1` до `20`.

Увеличение этих значений не гарантирует ускорение и может привести к ответам
Stepik `429 Too Many Requests`. Начните со значений по умолчанию.

Файл `.env` и файлы `*.db` уже исключены из Git через `.gitignore`.

## 5. Проверить локальный запуск

Проверить CLI без подключения клиента:

```sh
uv run --locked stepik-autopilot --help
```

Запустить сервер по Streamable HTTP:

```sh
uv run --locked stepik-autopilot \
  --transport http \
  --host 127.0.0.1 \
  --port 8000
```

После запуска MCP endpoint доступен по адресу
`http://127.0.0.1:8000/mcp`. При первом старте сервер создаст SQLite-схему.
Остановить его можно сочетанием `Ctrl+C`.

Сам факт старта проверяет формат `.env` и базу данных. OAuth-пара проверяется
при первом обращении к Stepik, например через `stepik_courses`.

Для одного локального клиента удобнее stdio: клиент сам запускает и останавливает
сервер. Именно этот вариант используется ниже.

## 6. Подключить MCP-клиент

Выберите только нужный вам подраздел. OAuth-секреты остаются в `.env`; копировать
их в конфигурацию Codex, Claude Code или Pi не нужно.

### Codex

Codex CLI, приложение Codex и расширение IDE используют общую MCP-конфигурацию.
Регистрация через CLI:

```sh
codex mcp add stepik-autopilot -- \
  /ABS/PATH/TO/uv \
  --directory /ABS/PATH/TO/stepik-autopilot-mcp \
  run --locked stepik-autopilot --transport stdio
```

Проверка:

```sh
codex mcp get stepik-autopilot
codex mcp list
```

После добавления перезапустите Codex или расширение IDE. В терминальном интерфейсе
Codex команда `/mcp` показывает состояние подключений.

Альтернатива — добавить сервер вручную в `~/.codex/config.toml`:

```toml
[mcp_servers.stepik-autopilot]
command = "/ABS/PATH/TO/uv"
args = [
  "--directory",
  "/ABS/PATH/TO/stepik-autopilot-mcp",
  "run",
  "--locked",
  "stepik-autopilot",
  "--transport",
  "stdio",
]
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Актуальный формат описан в
[официальной документации Codex MCP](https://developers.openai.com/codex/mcp).

### Claude Code

Добавьте сервер в пользовательскую область, чтобы он был доступен из любого
проекта:

```sh
claude mcp add \
  --transport stdio \
  --scope user \
  stepik-autopilot -- \
  /ABS/PATH/TO/uv \
  --directory /ABS/PATH/TO/stepik-autopilot-mcp \
  run --locked stepik-autopilot --transport stdio
```

Проверка:

```sh
claude mcp get stepik-autopilot
claude mcp list
```

Запустите новую сессию `claude` и выполните `/mcp`. Сервер должен иметь статус
`Connected`. Двойной дефис `--` перед `/ABS/PATH/TO/uv` обязателен: он отделяет
параметры Claude Code от команды MCP-сервера.

Подробнее: [официальная документация Claude Code MCP](https://code.claude.com/docs/en/mcp).

### Pi coding agent

Этот раздел относится к Pi с сайта [pi.dev](https://pi.dev/). В Pi нет
встроенного MCP-клиента, поэтому сначала требуется стороннее расширение.

Установите расширение:

```sh
pi install npm:pi-mcp-extension
```

> [!NOTE]
> Расширения Pi выполняют код с правами текущего пользователя. Перед установкой
> стороннего пакета рекомендуется проверить его исходный код.

Создайте глобальный файл `~/.pi/agent/mcp.json` или добавьте запись в уже
существующий файл:

```json
{
  "settings": {
    "requestTimeoutMs": 120000
  },
  "mcpServers": {
    "stepik-autopilot": {
      "transport": "stdio",
      "command": "/ABS/PATH/TO/uv",
      "args": [
        "--directory",
        "/ABS/PATH/TO/stepik-autopilot-mcp",
        "run",
        "--locked",
        "stepik-autopilot",
        "--transport",
        "stdio"
      ],
      "lifecycle": "eager"
    }
  }
}
```

Если `mcp.json` уже содержит другие серверы, не заменяйте весь файл: добавьте
`stepik-autopilot` внутрь существующего объекта `mcpServers`.

Перезапустите Pi и выполните `/mcp`. При `lifecycle: "eager"` сервер запускается
вместе с Pi. Команды `/mcp stepik-autopilot`,
`/mcp:start stepik-autopilot` и `/mcp:stop stepik-autopilot` показывают детали и
управляют подключением.

Используемое расширение передаёт Pi MCP tools, но пока не передаёт MCP prompts и
resources. Основной сценарий полностью доступен через tools; примеры обычных
запросов приведены ниже. Конфигурация расширения описана на
[странице пакета Pi](https://pi.dev/packages/pi-mcp-extension).

## 7. HTTP-вариант для нескольких клиентов

Не запускайте несколько stdio-процессов с одной базой одновременно. Если к
одному аккаунту и SQLite-базе должны подключаться несколько клиентов, запустите
один сервер:

```sh
/ABS/PATH/TO/uv \
  --directory /ABS/PATH/TO/stepik-autopilot-mcp \
  run --locked stepik-autopilot \
  --transport http --host 127.0.0.1 --port 8000
```

Затем подключите клиентов к `http://127.0.0.1:8000/mcp`.

Codex:

```sh
codex mcp add stepik-autopilot --url http://127.0.0.1:8000/mcp
```

Claude Code:

```sh
claude mcp add \
  --transport http \
  --scope user \
  stepik-autopilot http://127.0.0.1:8000/mcp
```

Pi, содержимое записи сервера в `mcp.json`:

```json
{
  "transport": "streamable-http",
  "url": "http://127.0.0.1:8000/mcp",
  "lifecycle": "eager"
}
```

> [!WARNING]
> Встроенной авторизации на HTTP endpoint сейчас нет. Оставляйте
> `--host 127.0.0.1` и не публикуйте порт в интернет или локальную сеть без
> отдельного защищённого reverse proxy и аутентификации.

## 8. Первый запуск в агенте

### Найти курс

Можно передать ID курса из URL:

```text
https://stepik.org/course/68343/...
                          ^^^^^
                       course_id
```

Или попросить агента использовать каталог:

```text
Покажи мои курсы Stepik через stepik_courses. Ничего не отправляй.
```

По умолчанию `stepik_courses` показывает курсы, на которые текущий аккаунт
записан. Можно искать по названию.

### Сначала построить безопасный план

```text
Проверь курс Stepik 68343 через stepik_plan. Покажи количество доступных,
пройденных, теоретических и неподдерживаемых заданий. Ничего не отправляй.
```

`stepik_plan` не создаёт attempts и submissions. В результате:

- `available` — доступные непройденные поддерживаемые задания;
- `passed` — уже пройденные практические задания;
- `unknown_progress` — задания, личный прогресс которых не удалось определить;
- `excluded_theory` — исключённые `text` и `video`;
- `unsupported` — непройденные практические типы без подтверждённого адаптера.

### Автоматически пройти оставшиеся тесты

```text
Пройди оставшиеся поддерживаемые задания курса Stepik 68343. Сначала покажи
план. Затем запусти autopilot с balanced, tasks_complete и deferred. Решай и
отправляй все пакеты, собирай результаты на границе раунда. Не отмечай лекции
прочитанными. Если оценка ещё pending, сообщи об этом и не отправляй ответ
повторно.
```

### Пройти только выбранные разделы

`section_numbers` — номера разделов в оглавлении курса, начиная с `1`:

```text
Проверь и пройди только разделы 1, 2 и 4 курса Stepik 68343. Используй
selection=explicit и section_numbers=[1, 2, 4]. Сначала покажи разрешённые
названия разделов и step_ids из stepik_plan.
```

Можно вместо разделов передать точные `explicit_step_ids`. Эти два способа
нельзя использовать одновременно.

### Сохранить ответы для проверки, не отправляя их

```text
Запусти курс Stepik 68343 в режиме review. Реши первый пакет и сохрани ответы
через action=save, но не отправляй их. Покажи вопросы, выбранные варианты и
draft_revision, затем жди моего подтверждения.
```

После проверки:

```text
Отправь без изменений сохранённую ревизию ответов для run_id <RUN_ID>. Затем
собери результаты.
```

### Продолжить прерванный запуск

Сохраните `run_id`, который вернул `stepik_run_start`, и попросите:

```text
Продолжи Stepik run <RUN_ID>: проверь status, выполни resume для сверки
неопределённых отправок, запроси незавершённый или следующий пакет и продолжи
работу без повторной отправки уже принятых ответов.
```

Для клиентов с MCP prompts доступны готовые prompts:

| Prompt | Назначение |
|---|---|
| `stepik_autopilot(course_id, target?)` | Полный автоматический цикл. |
| `stepik_review(course_id)` | Сохранение ответов перед подтверждением. |
| `stepik_tutor(course_id)` | По одному учебному пакету за раз. |
| `stepik_resume(run_id)` | Продолжение сохранённого запуска. |

## 9. Как устроен рабочий цикл

Обычный цикл клиента выглядит так:

1. `stepik_plan` проверяет курс без создания попыток.
2. `stepik_run_start` создаёт долговечный run и возвращает `run_id` вместе с
   `first_batch`.
3. Агент решает каждый вопрос пакета. В `selected_indexes` используются индексы
   вариантов с нуля: первый вариант — `0`, второй — `1`.
4. `stepik_batch_commit` сохраняет (`save`) или отправляет (`submit`) ответы.
5. `stepik_run_next` возвращает незавершённый пакет либо следующий пакет.
6. Когда `collect_required=true`, клиент вызывает `stepik_results_collect`.
7. `pending`, `review_required` и `outcome_unknown` не считаются неправильным
   ответом. Их нужно позже сверить, а не отправлять заново вслепую.

`request_id` обязателен для изменяющих и выдающих операции. Это уникальная
строка, которую создаёт клиент, например `start-68343-001` или
`commit-run123-002`. При безопасном повторе той же операции нужно повторно
использовать тот же `request_id` и тот же payload. Нельзя использовать прежний
`request_id` с другими аргументами.

Пример входа `stepik_run_start` в терминах MCP:

```json
{
  "arguments": {
    "course_id": "68343",
    "request_id": "start-68343-001",
    "mode": "autopilot",
    "strategy": "balanced",
    "target": "tasks_complete",
    "selection": "remaining",
    "grading": "deferred"
  }
}
```

Пример отправки одного ответа, где выбран первый вариант:

```json
{
  "arguments": {
    "run_id": "run_...",
    "request_id": "commit-run-001",
    "action": "submit",
    "answers": [
      {
        "item_id": "item_...",
        "answer": {
          "kind": "choice",
          "selected_indexes": [0]
        }
      }
    ]
  }
}
```

Для множественного выбора `selected_indexes` может содержать несколько
индексов. Передавайте ответы для всех элементов текущего пакета одним вызовом.

## 10. Параметры запуска

### Режим `mode`

| Значение | Использование |
|---|---|
| `autopilot` | Решить и сразу отправлять ответы. Значение по умолчанию. |
| `review` | Сначала сохранить ответы через `action="save"`, затем отправить подтверждённую `draft_revision`. |
| `tutor` | Клиент показывает пакет пользователю и действует как преподаватель. |
| `inspect` | Не используется в `run_start`; для чтения вызывайте `stepik_plan`. |

### Стратегия `strategy`

| Значение | Размер пакета |
|---|---:|
| `balanced` | до 8 заданий; значение по умолчанию |
| `throughput` | до 12 заданий |
| `economy` | до 6 заданий |

### Выбор `selection`

| Значение | Какие задания выбирать |
|---|---|
| `remaining` | Все доступные непройденные поддерживаемые задания. |
| `failed` | Актуальные неправильные и всё ещё непройденные задания. |
| `explicit` | Только `section_numbers` или только `explicit_step_ids`. |

`target` принимает `tasks_complete`, `all_available_tasks` или `score`;
`grading` — `deferred` или `immediate`. Для текущего основного сценария
рекомендуются проверенные значения по умолчанию `tasks_complete` и `deferred`.

## 11. Доступные MCP tools

| Tool | Что делает |
|---|---|
| `stepik_courses` | Показывает доступные курсы и поиск по названию. |
| `stepik_plan` | Читает структуру и прогресс курса без attempts. |
| `stepik_run_start` | Создаёт run и выдаёт первый пакет. |
| `stepik_run_next` | Возвращает активный или следующий пакет. |
| `stepik_batch_commit` | Сохраняет или отправляет ответы `choice`, `string`, `number` и `code`. |
| `stepik_results_collect` | Собирает оценки известных submissions. |
| `stepik_run_status` | Возвращает состояние run. |
| `stepik_run_control` | Выполняет `pause`, `resume` или `cancel`; `resume` также сверяет неопределённые отправки. |
| `stepik_read` | Читает приватные локальные ресурсы run, item и submission. |

`stepik_read` принимает URI следующих видов:

```text
stepik://runs/<run_id>
stepik://runs/<run_id>/items/<item_id>
stepik://runs/<run_id>/submissions/<submission_id>
```

## 12. Данные и безопасность

- OAuth credentials хранятся только в локальном `.env`.
- Access token запрашивается сервером и кэшируется в памяти; клиенту он не
  возвращается.
- SQLite-база содержит историю локальных запусков и отправок. Не публикуйте её,
  если считаете эти данные приватными.
- Для резервной копии остановите MCP-сервер и скопируйте файл базы, указанный в
  `DB__URL`.
- Один stdio-клиент запускает один процесс сервера. Для нескольких клиентов
  используйте один общий loopback HTTP-процесс.

## 13. Решение проблем

### `Stepik OAuth token request failed`

- проверьте `STEPIK__OAUTH__CLIENT_ID` и
  `STEPIK__OAUTH__CLIENT_SECRET`;
- убедитесь, что OAuth-приложение создано в нужном аккаунте с grant type
  `Client credentials`;
- убедитесь, что в значениях `.env` нет лишних кавычек или пробелов;
- проверьте доступ к `https://stepik.org`.

### MCP-клиент не видит сервер

- замените оба `/ABS/PATH/...` реальными абсолютными путями;
- проверьте запуск `uv run --locked stepik-autopilot --help` в корне проекта;
- выполните `codex mcp list`, `claude mcp list` или `/mcp` в Pi;
- перезапустите клиент после изменения конфигурации;
- для Pi проверьте, что `pi-mcp-extension` установлен и JSON синтаксически
  корректен.

### Курс не найден или список пуст

- проверьте, что OAuth-приложение принадлежит нужному аккаунту;
- убедитесь, что этот аккаунт записан на курс;
- передайте точный `course_id` из URL;
- для поиска общедоступных курсов попросите вызвать `stepik_courses` с
  `enrolled_only=false`.

### План есть, но доступных заданий нет

Это нормально, если задания уже пройдены, закрыты условиями курса или имеют пока
неподдерживаемый тип. Смотрите поля `passed`, `unknown_progress`,
`excluded_theory`, `unsupported` и список `task_types` в результате плана.

### Результат остаётся `pending`

Stepik мог ещё не закончить проверку. Позже повторите `stepik_results_collect`.
Не создавайте новую отправку только из-за `pending`, `evaluation`,
`review_required` или `outcome_unknown`.

## 14. Обновление и разработка

Обновить локальную копию:

```sh
git pull
uv sync --locked --all-groups
```

После обновления перезапустите MCP-клиент или общий HTTP-сервер.

Проверки проекта:

```sh
uv run ruff format --check src tests
uv run ruff check src tests
uv run basedpyright src tests
uv run pytest -q
```

Архитектура, контракты и план развития описаны в [DESIGN.md](DESIGN.md).
