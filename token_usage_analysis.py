#!/usr/bin/env python3
"""
Анализ использования токенов и паттернов вызовов Hermes Agent
Собирает данные из:
1. Логов hermes-gateway (journalctl)
2. БД postgres (canonical memory)
3. Метрик prometheus (если доступны)
"""

import json
import re
import subprocess
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import psycopg2
from pathlib import Path

# Загрузка credentials
def load_env(path="/srv/automation/.env"):
    env = {}
    if Path(path).exists():
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k] = v.strip('"\'')
    return env

# Подключение к БД
def get_db_conn():
    env = load_env()
    return psycopg2.connect(
        host="127.0.0.1",
        port=5432,
        dbname="postgres",
        user=env.get("POSTGRES_USER", "automation"),
        password=env.get("POSTGRES_PASSWORD", ""),
        options="-c search_path=automation,public"
    )

# Анализ логов hermes-gateway за последние 7 дней
def analyze_gateway_logs(days=7):
    since = f"{days} days ago"
    cmd = [
        "sudo", "journalctl",
        "-u", "hermes-gateway.service",
        "--since", since,
        "--no-pager",
        "-o", "cat"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    logs = result.stdout
    
    stats = {
        "total_requests": 0,
        "models_used": Counter(),
        "providers_used": Counter(),
        "errors": Counter(),
        "token_estimates": defaultdict(int),
        "request_types": Counter()
    }
    
    # Паттерны для извлечения данных
    model_pattern = re.compile(r'"model":\s*"([^"]+)"')
    provider_pattern = re.compile(r'"provider":\s*"([^"]+)"')
    error_pattern = re.compile(r'(429|402|500|503|timeout|rate.?limit)', re.IGNORECASE)
    token_pattern = re.compile(r'"usage":\s*\{[^}]*"total_tokens":\s*(\d+)')
    
    for line in logs.split('\n'):
        if not line.strip():
            continue
            
        # Подсчет запросов
        if 'POST /v1/chat/completions' in line or 'streaming' in line.lower():
            stats["total_requests"] += 1
        
        # Модели
        if match := model_pattern.search(line):
            model = match.group(1)
            stats["models_used"][model] += 1
        
        # Провайдеры
        if match := provider_pattern.search(line):
            provider = match.group(1)
            stats["providers_used"][provider] += 1
        
        # Ошибки
        if match := error_pattern.search(line):
            error_type = match.group(1)
            stats["errors"][error_type] += 1
        
        # Токены
        if match := token_pattern.search(line):
            tokens = int(match.group(1))
            # Попробуем найти модель в той же строке
            model_match = model_pattern.search(line)
            model_key = model_match.group(1) if model_match else "unknown"
            stats["token_estimates"][model_key] += tokens
    
    return stats

# Анализ данных из БД
def analyze_db_usage():
    conn = get_db_conn()
    cur = conn.cursor()
    
    stats = {
        "artifact_versions_last_7d": 0,
        "insights_last_7d": 0,
        "ingestion_jobs_last_7d": 0,
        "top_projects": [],
        "top_workspaces": []
    }
    
    # Активность за последние 7 дней
    seven_days_ago = datetime.now() - timedelta(days=7)
    
    cur.execute("""
        SELECT COUNT(*) FROM artifact_versions 
        WHERE created_at >= %s
    """, (seven_days_ago,))
    stats["artifact_versions_last_7d"] = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM insights 
        WHERE created_at >= %s
    """, (seven_days_ago,))
    stats["insights_last_7d"] = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM ingestion_jobs 
        WHERE created_at >= %s
    """, (seven_days_ago,))
    stats["ingestion_jobs_last_7d"] = cur.fetchone()[0]
    
    # Топ проектов по активности
    cur.execute("""
        SELECT p.name, w.name as workspace, COUNT(av.id) as versions
        FROM projects p
        JOIN workspaces w ON p.workspace_id = w.id
        LEFT JOIN artifacts a ON a.project_id = p.id
        LEFT JOIN artifact_versions av ON av.artifact_id = a.id
        WHERE av.created_at >= %s
        GROUP BY p.name, w.name
        ORDER BY versions DESC
        LIMIT 10
    """, (seven_days_ago,))
    stats["top_projects"] = [
        {"project": row[0], "workspace": row[1], "versions": row[2]}
        for row in cur.fetchall()
    ]
    
    cur.close()
    conn.close()
    
    return stats

# Анализ паттернов delegate_task
def analyze_delegation_patterns():
    """
    Ищет паттерны использования delegate_task в логах
    """
    cmd = [
        "sudo", "journalctl",
        "-u", "hermes-gateway.service",
        "--since", "7 days ago",
        "--no-pager",
        "-o", "cat"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    logs = result.stdout
    
    stats = {
        "delegate_task_calls": 0,
        "parallel_tasks": 0,
        "subagent_models": Counter()
    }
    
    for line in logs.split('\n'):
        if 'delegate_task' in line.lower():
            stats["delegate_task_calls"] += 1
            
            # Попытка найти модель субагента
            if '"model"' in line:
                model_match = re.search(r'"model":\s*"([^"]+)"', line)
                if model_match:
                    stats["subagent_models"][model_match.group(1)] += 1
        
        if 'tasks' in line and '[' in line:
            # Параллельные задачи
            stats["parallel_tasks"] += 1
    
    return stats

# Главная функция
def main():
    print("=" * 80)
    print("АНАЛИЗ ИСПОЛЬЗОВАНИЯ ТОКЕНОВ И ПАТТЕРНОВ HERMES AGENT")
    print("=" * 80)
    print()
    
    print("📊 Сбор данных из логов hermes-gateway...")
    gateway_stats = analyze_gateway_logs(days=7)
    
    print("📊 Сбор данных из БД...")
    db_stats = analyze_db_usage()
    
    print("📊 Анализ паттернов делегирования...")
    delegation_stats = analyze_delegation_patterns()
    
    # Формирование отчета
    report = {
        "timestamp": datetime.now().isoformat(),
        "period_days": 7,
        "gateway_stats": {
            "total_requests": gateway_stats["total_requests"],
            "models_used": dict(gateway_stats["models_used"].most_common(10)),
            "providers_used": dict(gateway_stats["providers_used"]),
            "errors": dict(gateway_stats["errors"]),
            "token_estimates": dict(gateway_stats["token_estimates"])
        },
        "db_stats": db_stats,
        "delegation_stats": {
            "delegate_task_calls": delegation_stats["delegate_task_calls"],
            "parallel_tasks": delegation_stats["parallel_tasks"],
            "subagent_models": dict(delegation_stats["subagent_models"].most_common(5))
        }
    }
    
    # Вывод отчета
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ АНАЛИЗА")
    print("=" * 80)
    print()
    
    print("🔹 Gateway статистика (последние 7 дней):")
    print(f"  Всего запросов: {report['gateway_stats']['total_requests']}")
    print(f"  Использованные модели:")
    for model, count in report['gateway_stats']['models_used'].items():
        print(f"    - {model}: {count} запросов")
    
    print(f"\n  Провайдеры:")
    for provider, count in report['gateway_stats']['providers_used'].items():
        print(f"    - {provider}: {count} запросов")
    
    print(f"\n  Ошибки:")
    for error, count in report['gateway_stats']['errors'].items():
        print(f"    - {error}: {count} раз")
    
    print(f"\n  Оценка токенов по моделям:")
    total_tokens = sum(report['gateway_stats']['token_estimates'].values())
    print(f"    ВСЕГО: ~{total_tokens:,} токенов")
    for model, tokens in sorted(report['gateway_stats']['token_estimates'].items(), 
                                 key=lambda x: x[1], reverse=True):
        print(f"    - {model}: ~{tokens:,} токенов")
    
    print(f"\n🔹 БД активность:")
    print(f"  Новых версий артефактов: {report['db_stats']['artifact_versions_last_7d']}")
    print(f"  Новых insights: {report['db_stats']['insights_last_7d']}")
    print(f"  Новых ingestion jobs: {report['db_stats']['ingestion_jobs_last_7d']}")
    
    print(f"\n  Топ-5 активных проектов:")
    for proj in report['db_stats']['top_projects'][:5]:
        print(f"    - {proj['workspace']}/{proj['project']}: {proj['versions']} версий")
    
    print(f"\n🔹 Паттерны делегирования:")
    print(f"  Вызовов delegate_task: {report['delegation_stats']['delegate_task_calls']}")
    print(f"  Параллельных задач: {report['delegation_stats']['parallel_tasks']}")
    print(f"  Модели субагентов:")
    for model, count in report['delegation_stats']['subagent_models'].items():
        print(f"    - {model}: {count} раз")
    
    # Сохранение отчета
    output_path = "/home/Bilirubin/workspace/token_usage_report.json"
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Полный отчет сохранен: {output_path}")
    
    # Рекомендации
    print("\n" + "=" * 80)
    print("💡 ПРЕДВАРИТЕЛЬНЫЕ РЕКОМЕНДАЦИИ")
    print("=" * 80)
    
    if total_tokens > 1_000_000:
        print("⚠️  Высокое потребление токенов (>1M за неделю)")
        print("   Рекомендуется внедрить агрессивное кэширование и использование дешевых моделей")
    
    if report['gateway_stats']['errors']:
        print(f"⚠️  Обнаружены ошибки: {sum(report['gateway_stats']['errors'].values())} случаев")
        print("   Необходим fallback механизм для обработки rate limits")
    
    if len(report['gateway_stats']['providers_used']) == 1:
        print("⚠️  Используется только один провайдер")
        print("   Критически важно добавить резервные провайдеры")

if __name__ == "__main__":
    main()
