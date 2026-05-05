# Рекомендации по улучшению инфраструктуры career-odyssey-vm

**Дата:** 2026-05-03  
**Текущее состояние:** Все сервисы работают, проблемы устранены, инфраструктура стабильна

---

## 🔴 HIGH PRIORITY

### 1. Автоматические бэкапы Postgres (Easy)
**Проблема:** Нет автоматических бэкапов БД (rag + n8n, 23MB total)  
**Риск:** Потеря данных при сбое диска/VM  
**Решение:**
```bash
# Создать скрипт /usr/local/bin/postgres_backup.sh
#!/bin/bash
BACKUP_DIR="/home/Bilirubin/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup обеих БД
docker exec automation-postgres pg_dump -U automation -d rag -Fc > $BACKUP_DIR/rag_$DATE.dump
docker exec automation-postgres pg_dump -U automation -d n8n -Fc > $BACKUP_DIR/n8n_$DATE.dump

# Удалить бэкапы старше 7 дней
find $BACKUP_DIR -name "*.dump" -mtime +7 -delete

# Опционально: загрузить в GCS
# gsutil cp $BACKUP_DIR/*_$DATE.dump gs://career-odyssey-backups/postgres/
```

**Systemd timer:**
```ini
# /etc/systemd/system/postgres-backup.timer
[Unit]
Description=Daily Postgres backup

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Оценка:** 30 минут, экономия ~20MB диска (ротация), критично для disaster recovery

---

### 2. HTTPS + Let's Encrypt (Medium)
**Проблема:** Nginx слушает только HTTP :80, нет шифрования  
**Риск:** Credentials передаются открытым текстом, MITM атаки  
**Решение:**
```bash
# Установить certbot
sudo apt-get install certbot python3-certbot-nginx

# Получить сертификат (требуется домен, сейчас только IP)
# Вариант 1: Купить домен ($12/год) + настроить DNS A-record
# Вариант 2: Использовать бесплатный DuckDNS/NoIP

# После настройки домена:
sudo certbot --nginx -d your-domain.com

# Auto-renewal уже настроен через systemd timer
```

**Альтернатива (без домена):** Self-signed cert для внутреннего использования  
**Оценка:** 1-2 часа (с доменом), критично для безопасности

---

### 3. Rate Limiting в Nginx (Easy)
**Проблема:** Нет защиты от DDoS/brute-force на публичных endpoints  
**Риск:** Перегрузка сервера, превышение квот провайдеров  
**Решение:**
```nginx
# Добавить в /etc/nginx/sites-enabled/n8n.conf
http {
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=webhook_limit:10m rate=30r/m;
    
    server {
        location = /orchestrate {
            limit_req zone=webhook_limit burst=5 nodelay;
            # ... existing proxy_pass
        }
        
        location = /rag-search {
            limit_req zone=api_limit burst=10 nodelay;
            # ... existing proxy_pass
        }
    }
}
```

**Оценка:** 15 минут, защита от abuse

---

### 4. Мониторинг дискового пространства с алертами (Easy)
**Проблема:** Диск 71%, нет автоматических алертов при достижении порога  
**Риск:** Заполнение диска → сбой сервисов  
**Решение:**
```python
# Добавить в /usr/local/bin/resource_monitor.py
DISK_THRESHOLD = 80  # %
if disk_usage > DISK_THRESHOLD:
    send_telegram_alert(f"⚠️ Диск заполнен на {disk_usage}%")
    # Автоматическая очистка:
    # - docker system prune -f
    # - journalctl --vacuum-time=3d
    # - find /tmp -mtime +3 -delete
```

**Оценка:** 20 минут, предотвращение простоя

---

## ⚠️ MEDIUM PRIORITY

### 5. Grafana Dashboard (Medium)
**Проблема:** Prometheus собирает метрики, но нет визуализации  
**Решение:**
```bash
# Установить Grafana (легковесный, ~50MB RAM)
docker run -d --name=grafana \
  -p 127.0.0.1:3000:3000 \
  -v grafana-storage:/var/lib/grafana \
  --restart=unless-stopped \
  grafana/grafana-oss:latest

# Импортировать готовые дашборды:
# - Node Exporter Full (ID: 1860)
# - n8n Metrics (custom)
```

**Оценка:** 1 час, улучшает observability

---

### 6. Postgres Connection Pooling (Medium)
**Проблема:** Прямые подключения к Postgres, нет пулинга  
**Риск:** Исчерпание connections при нагрузке  
**Решение:**
```bash
# Добавить PgBouncer в docker-compose.yml
pgbouncer:
  image: pgbouncer/pgbouncer:latest
  environment:
    DATABASES_HOST: automation-postgres
    DATABASES_PORT: 5432
    DATABASES_USER: automation
    PGBOUNCER_POOL_MODE: transaction
    PGBOUNCER_MAX_CLIENT_CONN: 100
    PGBOUNCER_DEFAULT_POOL_SIZE: 20
  ports:
    - "127.0.0.1:6432:6432"
```

**Оценка:** 1 час, улучшает производительность под нагрузкой

---

### 7. Structured Logging (Medium)
**Проблема:** Логи в plain text, сложно парсить и анализировать  
**Решение:**
```python
# Перевести все скрипты на structured JSON logging
import structlog
logger = structlog.get_logger()
logger.info("service_started", service="hermes-gateway", port=8642)

# Настроить Loki для агрегации логов (опционально)
```

**Оценка:** 2-3 часа, улучшает debugging

---

### 8. Secrets Management (Medium)
**Проблема:** Секреты в plain text .env файлах  
**Решение:**
```bash
# Вариант 1: Encrypted .env с age/sops
age-keygen -o ~/.hermes/age.key
age -e -r $(cat ~/.hermes/age.key.pub) .env > .env.age

# Вариант 2: GCP Secret Manager (бесплатно до 10k операций/мес)
gcloud secrets create OPENROUTER_API_KEY --data-file=-
# Читать через gcloud secrets versions access latest
```

**Оценка:** 1-2 часа, улучшает безопасность

---

### 9. n8n Self-Healing Loop — диагностика и исправление (Hard)
**Проблема:** Workflow отключен из-за 93% ошибок  
**Решение:**
1. Экспортировать workflow JSON из n8n UI
2. Проанализировать логи последних executions
3. Исправить проблемные узлы (вероятно, неверные credentials или endpoints)
4. Протестировать вручную
5. Реактивировать

**Оценка:** 2-4 часа, восстановление автоматического self-healing

---

## 🟢 LOW PRIORITY (Nice to Have)

### 10. Redis для кеширования (Medium)
**Проблема:** Нет кеша для частых запросов (RAG search, embeddings)  
**Решение:**
```bash
docker run -d --name redis \
  -p 127.0.0.1:6379:6379 \
  -v redis-data:/data \
  --restart=unless-stopped \
  redis:alpine redis-server --maxmemory 100mb --maxmemory-policy allkeys-lru
```

**Оценка:** 1 час + интеграция в код, ускорение на 50-90%

---

### 11. CI/CD Pipeline (Hard)
**Проблема:** Ручной деплой изменений  
**Решение:**
```yaml
# .github/workflows/deploy.yml
name: Deploy to GCP
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy via SSH
        run: |
          ssh user@34.133.31.146 'cd /srv/automation && git pull && docker-compose up -d'
```

**Оценка:** 3-4 часа, автоматизация деплоя

---

### 12. Swap на SSD вместо HDD (Easy, но требует рестарт)
**Проблема:** Swap на медленном HDD (pd-standard), влияет на производительность  
**Решение:**
```bash
# Создать swap на tmpfs (RAM-backed, быстрее)
# Или: upgrade диска до pd-ssd (дороже на $0.68/мес за 20GB)
```

**Оценка:** 30 минут, улучшение latency при swap usage

---

### 13. Prometheus Alertmanager (Medium)
**Проблема:** Prometheus собирает метрики, но не отправляет алерты  
**Решение:**
```yaml
# docker-compose.yml
alertmanager:
  image: prom/alertmanager:latest
  volumes:
    - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
  ports:
    - "127.0.0.1:9093:9093"

# alertmanager.yml
route:
  receiver: telegram
receivers:
  - name: telegram
    telegram_configs:
      - bot_token: $TELEGRAM_BOT_TOKEN
        chat_id: 322158958
```

**Оценка:** 1-2 часа, проактивные алерты

---

### 14. Документация API endpoints (Easy)
**Проблема:** Нет OpenAPI/Swagger документации для /orchestrate, /rag-search  
**Решение:**
```python
# Добавить FastAPI + Swagger UI для automation-gateway
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI()
# ... existing routes

@app.get("/docs")
def custom_openapi():
    return get_openapi(title="Automation Gateway API", version="1.0.0", routes=app.routes)
```

**Оценка:** 1 час, улучшает developer experience

---

### 15. Postgres VACUUM и ANALYZE автоматизация (Easy)
**Проблема:** Нет регулярного VACUUM, таблицы могут раздуваться  
**Решение:**
```sql
-- Включить autovacuum (обычно включен по умолчанию)
ALTER SYSTEM SET autovacuum = on;
SELECT pg_reload_conf();

-- Или добавить в cron:
0 4 * * * docker exec automation-postgres psql -U automation -d rag -c "VACUUM ANALYZE;"
```

**Оценка:** 10 минут, поддержка производительности БД

---

## 📊 ИТОГОВАЯ ОЦЕНКА

**Быстрые победы (1-2 часа):**
1. Postgres backups (30 мин)
2. Rate limiting (15 мин)
3. Disk monitoring alerts (20 мин)
4. Postgres VACUUM automation (10 мин)

**Критично для production (4-6 часов):**
1. HTTPS + Let's Encrypt (2 часа)
2. Secrets management (1-2 часа)
3. Grafana dashboard (1 час)
4. n8n Self-Healing Loop fix (2-4 часа)

**Долгосрочные улучшения (8-12 часов):**
1. Redis caching (1 час + интеграция)
2. CI/CD pipeline (3-4 часа)
3. Structured logging (2-3 часа)
4. Prometheus Alertmanager (1-2 часа)

**Общая оценка текущей инфраструктуры:** 7/10
- ✅ Все сервисы работают
- ✅ Мониторинг настроен (Prometheus + node-exporter)
- ✅ Автоматический health loop
- ⚠️ Нет backups
- ⚠️ Нет HTTPS
- ⚠️ Нет rate limiting
- ⚠️ Нет визуализации метрик

**После внедрения High Priority рекомендаций:** 9/10 (production-ready)
