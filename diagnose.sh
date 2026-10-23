#!/usr/bin/env bash
# Диагностика Telegram-связки BIOTORF OS. Запуск: bash diagnose.sh
set -u
YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC} $1"; }
bad()  { echo -e "${RED}[!!]${NC} $1"; }
warn() { echo -e "${YELLOW}[?]${NC} $1"; }

echo "── 1. Контейнеры ──────────────────────────────"
docker ps --format '{{.Names}}: {{.Status}}' | grep biotorf || bad "Контейнеры biotorf не запущены. Выполните: docker compose up -d --build"
docker ps --format '{{.Names}}' | grep -q biotorf-tg-worker \
  && ok "telegram-worker запущен" \
  || bad "Нет контейнера biotorf-tg-worker. Запуск: docker compose --profile tg up -d"

echo; echo "── 2. Переменные в .env ───────────────────────"
if [ ! -f .env ]; then bad "Файл .env не найден! Скопируйте: cp .env.example .env и заполните TELEGRAM_BOT_TOKEN"; else
  TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env | cut -d= -f2-)
  SECRET=$(grep -E '^TELEGRAM_WEBHOOK_SECRET=' .env | cut -d= -f2-)
  if [ -z "$TOKEN" ]; then bad "TELEGRAM_BOT_TOKEN пуст в .env — вставьте токен от @BotFather (формат 123456:AAA...)"; else ok "Токен задан (${#TOKEN} симв.)"; fi
  # частые ошибки токена
  case "$TOKEN" in *" "*|*$'\r'*) bad "В токене есть пробел/невидимый символ — перепечатайте его в .env";; esac
fi

echo; echo "── 3. Живой тест токена (getMe) ───────────────"
if [ -n "${TOKEN:-}" ]; then
  R=$(curl -s --max-time 10 "https://api.telegram.org/bot$TOKEN/getMe")
  if echo "$R" | grep -q '"ok":true'; then
    ok "Токен валиден, бот: $(echo "$R" | grep -o '"username":"[^"]*"')"
  else
    bad "Telegram отверг токен: $R"
    warn "Проверьте: скопирован весь токен без лишних символов? Бот не удалён?"
  fi
fi

echo; echo "── 4. Логи telegram-worker ────────────────────"
docker logs biotorf-tg-worker --tail 15 2>&1 || warn "не удалось прочитать логи"
echo "  подсказки:"
echo "   • 'Conflict: terminated by other getUpdates' (409) — где-то ещё крутится polling/webhook."
echo "     Воркер сам делает deleteWebhook при старте; если не помогло: @BotFather -> /deletewebhook"
echo "   • 'Not Found' в логах backend — секрет воркера != секрет бэкенда (оба из TELEGRAM_WEBHOOK_SECRET)."

echo; echo "── 5. Вебхук принимает ли сообщения ───────────"
if [ -n "${SECRET:-}" ]; then
  docker exec biotorf-backend sh -c "wget -q -O- --post-data='{\"update_id\":999999001,\"message\":{\"message_id\":1,\"date\":0,\"chat\":{\"id\":1,\"type\":\"private\",\"first_name\":\"Диагностика\"},\"from\":{\"id\":1,\"is_bot\":false,\"first_name\":\"Диагностика\"},\"text\":\"ТЕСТ диагностика\"}}' --header='Content-Type: application/json' --header='X-Bot-Secret: $SECRET' http://localhost:8787/webhooks/telegram" 2>/dev/null \
    && ok "Бэкенд принимает вебхук" || bad "Бэкенд не принял тестовое сообщение (см. docker logs biotorf-backend)"
fi

echo; echo "── 6. Лента comms ─────────────────────────────"
curl -s --max-time 5 "http://localhost:8787/api/comms?limit=5" | head -c 600 || curl -s --max-time 5 "http://localhost:8080/api/comms?limit=5" | head -c 600
echo; echo "Если последние 2 шага OK, но реальных сообщений нет — пишите боту в ЛИЧНЫЙ чат"
echo "(в группах с включённым privacy mode бот видит только команды /)."
