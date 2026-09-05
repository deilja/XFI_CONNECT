# XFI CONNECT

Telegram-бот и backend VPN-сервиса XFI для управления подписками, выдачи VPN-конфигураций, поддержки пользователей и интеграции с XFI AI.

## Возможности

- продажа и управление VPN-подписками;
- выдача и управление VPN-ссылками и конфигурациями;
- поддержка WireGuard, AmneziaWG, VLESS/Reality и Xray-сценариев;
- административные инструменты через Telegram;
- интеграция с 3X-UI/X-UI;
- встроенный AI-помощник через XFI AI Gateway;
- безопасная настройка XFI AI API token через `/ai_token`;
- поддержка клиентских приложений Happ, Hiddify Next, v2RayTun, Amnezia и Incy;
- инструкции пользователю по подключению и импорту подписки;
- Telegram support workflow;
- приём событий Trial VPN через существующий webhook backend без отдельного Telegram Bot Token.

## Trial VPN

После выдачи тестовой подписки сервис `deilja/trial-vpn` может отправить событие в существующий XFI CONNECT backend. Trial VPN не хранит Telegram Bot Token и не отправляет сообщения в Telegram напрямую.

Endpoint:

```text
POST /custom-payment-webhook/trial-vpn
```

Доступ защищается `TRIAL_VPN_WEBHOOK_SECRET`. После получения события XFI CONNECT использует существующий admin notification path. Подробная схема настройки: `docs/TRIAL_VPN_WEBHOOK.md`.

## XFI AI

XFI CONNECT подключается к XFI AI Gateway по одному клиентскому `xfi_...` токену. Реальные API keys AI-провайдеров в XFI CONNECT не хранятся.

### Настройка

Администратор получает токен в Telegram-боте XFI AI:

```text
/token
```

Затем в XFI CONNECT:

```text
/ai_token xfi_...
```

Токен перед сохранением проверяется через XFI AI Gateway. После успешной проверки сообщение с токеном удаляется из чата, когда Telegram разрешает удаление.

Хранилище токена задаётся через `XFI_AI_TOKEN_FILE`. По умолчанию используется:

```text
data/xfi_ai_gateway_token
```

Новые запросы `/ai` используют актуальное значение токена без перезапуска бота.

## AI-помощник

Команда:

```text
/ai <вопрос>
```

AI-помощник отвечает по вопросам эксплуатации XFI VPN и связанных технологий: WireGuard, AmneziaWG, VLESS/Reality, Xray, 3X-UI, VPN-клиенты и диагностика.

Ответы разбиваются на безопасные для Telegram части с ограничением размера сообщения.

## XFI AI Code Agent

Отдельный Telegram-бот XFI AI может изменять код XFI CONNECT по обычному текстовому запросу администратора.

Цикл работы:

```text
Запрос
  ↓
анализ репозитория
  ↓
уточняющие вопросы
  ↓
план и список файлов
  ↓
ПОДТВЕРЖДАЮ
  ↓
ветка xfi-ai/*
  ↓
изменения
  ↓
Pull Request
  ↓
GitHub Actions
```

Прямые изменения `main` для этого сценария не выполняются. XFI AI работает через отдельную ветку и Pull Request.

## Клиенты

Поддерживаются сценарии подключения через Happ, Hiddify Next, v2RayTun, Amnezia, Incy и WireGuard-конфигурацию.

Для Incy предусмотрен автоматический импорт по ссылке подписки, где это поддерживается текущей конфигурацией бота.

## Переменные окружения XFI AI

```env
XFI_AI_BASE_URL=http://127.0.0.1:8091
XFI_AI_TOKEN_FILE=data/xfi_ai_gateway_token
XFI_AI_API_KEY=
XFI_AI_MODEL=
XFI_AI_TIMEOUT=45
```

`XFI_AI_API_KEY` используется как fallback, если файл токена недоступен.

## Безопасность

- XFI AI token проверяется до сохранения.
- Реальные ключи AI-провайдеров не передаются пользователям XFI CONNECT.
- Административные команды проверяются через существующую admin authorization.
- Code Agent не записывает изменения непосредственно в `main`.
- Изменение кода выполняется только после явного подтверждения `ПОДТВЕРЖДАЮ`.
- Trial VPN webhook защищён отдельным shared secret.
- Trial VPN webhook не принимает и не пересылает subscription URL или UUID клиента.

## Разработка

Python 3.12+.

Установка зависимостей:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Проверка синтаксиса:

```bash
python3 -m compileall -q .
```

Проверка lint:

```bash
python3 -m ruff check .
```

Тесты:

```bash
python3 -m pytest -q
```

## CI

GitHub Actions выполняет проверку Python-кода, compile check, lint и regression suite.

## Связанные проекты

- XFI AI — AI Gateway, provider failover, VPS control и Code Agent.
- XFI Guard — мониторинг и защита VPS-инфраструктуры XFI.

## Лицензия

Лицензия и условия использования определяются файлами текущего репозитория.
