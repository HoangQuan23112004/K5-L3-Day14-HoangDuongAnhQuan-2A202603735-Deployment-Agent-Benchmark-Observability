# Deployment Information — Day 14

## Public URL
https://quanhda.onrender.com

## Platform
Render (Web Service — Docker runtime, Root Directory: `06-lab-complete`, kèm Render Key Value / Redis)

## Test Commands

Đặt biến môi trường trước khi chạy (không ghi secret trực tiếp vào repo):

```bash
export BASE="https://quanhda.onrender.com"
export AGENT_API_KEY="<YOUR_AGENT_API_KEY>"
```

### 1. Health Check (Liveness)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# Expected: 200
# Body: {"status":"ok","uptime_seconds":...,"environment":"production"}
```

### 2. Readiness Check (Redis Connected)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# Expected: 200
# Body: {"status":"ready","redis":"connected"}
```

### 3. API Test — Không có API Key (Unauthorized)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'
# Expected: 401
```

### 4. API Test — Có API Key (Authorized)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
# Expected: 200
```

## Environment Variables Set (trên Render Dashboard)
- `ENVIRONMENT` (`production`)
- `AGENT_API_KEY` *(secret — cấu hình trên Render, không lưu trong Git)*
- `REDIS_URL` *(Internal Key Value URL của Redis trên Render)*
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)
- `LOG_LEVEL` (`INFO`)
- `PORT` *(Render tự inject)*

## Screenshots
- [Deployment dashboard & live logs](screenshots/dashboard.png)
- [Service running (Live)](screenshots/running.png)
- [Test results (200 / 200 / 401 / 200)](screenshots/test.png)
