# Day 14 Lab — Mission Answers

> **Họ và tên:** Hoàng Dương Anh Quân  
> **MSSV:** 2A202603735  
> **Lớp:** K5-L3  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Các anti-pattern trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code** (dòng 17–18): `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`. Nếu push lên GitHub (nhất là repo public), secret bị lộ ngay lập tức.
2. **Không có config management qua environment variables** (dòng 21–22): Các biến cấu hình như `DEBUG = True`, `MAX_TOKENS = 500` được gán cứng trong code, không thể thay đổi giữa môi trường dev/staging/production mà không sửa code.
3. **Dùng `print()` thay cho structured logging và log ra secret** (dòng 33–34, 38): `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key ra stdout/log, đồng thời `print()` không có timestamp, log level hay format JSON để các hệ thống thu thập log phân tích.
4. **Thiếu endpoint health check (`/health`, `/ready`)** (dòng 42–43): Platform (Railway/Render/Kubernetes) hoặc load balancer không thể kiểm tra service còn sống hay đã sẵn sàng nhận traffic để tự động restart hoặc điều hướng.
5. **Bind `host="localhost"`, port cứng `8000` và bật `reload=True`** (dòng 49–54):
   - `host="localhost"` chỉ lắng nghe loopback bên trong máy/container, bên ngoài container không truy cập được.
   - `port=8000` không đọc biến môi trường `PORT` do cloud platform cấp động.
   - `reload=True` tốn tài nguyên theo dõi file và không an toàn trong production.

---

### Exercise 1.2: Kết quả chạy & test API

**Bản `develop` (`POST /ask?question=Hello`):**
```text
$ curl -X POST "http://localhost:8000/ask?question=Hello"
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

**Bản `production` (`GET /health` & `POST /ask`):**
```text
$ curl http://localhost:8000/health
{"status":"ok","uptime_seconds":31.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:56:14.484315+00:00"}

$ curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "Hello"}'
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","model":"gpt-4o-mini"}
```

---

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Tiêu chí | `develop/app.py` | `production/app.py` | Tại sao quan trọng trong Production? |
| :--- | :--- | :--- | :--- |
| **Secrets & Config** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trực tiếp trong code. | Đọc qua `settings` (từ environment variables / `.env`). | Tránh lộ mật khẩu/API key trên Git; đổi cấu hình theo môi trường mà không cần sửa code. |
| **Logging** | Dùng `print(...)`, log cả `OPENAI_API_KEY`. | Dùng `logging` format JSON có `time`, `level`, `msg`; chỉ log `question_length` và `client_ip`, không log secret. | Dễ tìm kiếm/lọc log trên hệ thống tập trung (Loki, Datadog) và đảm bảo bảo mật dữ liệu. |
| **Health Check** | Không có `/health` hay `/ready`. | Có `GET /health` trả về `status`, `uptime_seconds`, `version`, `environment`, `timestamp`. | Load balancer và cloud platform dựa vào đây để biết khi nào container sống và sẵn sàng nhận request. |
| **Lifecycle / Shutdown** | Không có xử lý startup/shutdown. | Dùng `lifespan` context manager để khởi tạo khi startup và dọn dẹp (`is_ready = False`, đợi request đang chạy) khi shutdown. | Tránh ngắt ngang kết nối của người dùng đang chờ phản hồi khi restart hoặc deploy phiên bản mới. |
| **Host, Port & Reload** | `host="localhost"`, `port=8000`, `reload=True`. | Bind `0.0.0.0`, đọc `PORT` từ `settings.port`, tắt `reload` ở production. | Container cần `0.0.0.0` để nhận traffic từ ngoài; Cloud platform cấp `PORT` động qua biến môi trường. |
| **CORS & Input** | Không cấu hình CORS; nhận `question` qua query string. | Cấu hình `CORSMiddleware` theo `allowed_origins`; nhận JSON body và validate trả `422` nếu thiếu `question`. | Kiểm soát domain được phép gọi API và chuẩn hóa API contract. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)
1. **Base image:** `python:3.11` (bản đầy đủ ~1 GB, chứa nhiều công cụ build nên image cuối rất lớn).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` đứng trước `COPY app.py`?** Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn source code; nếu đặt trước, khi sửa `app.py` thì Docker chỉ build lại từ bước `COPY app.py`, không phải chạy lại `pip install` tốn thời gian.
4. **Command chạy khi container khởi động:** `CMD ["python", "app.py"]` (mở port `8000` qua `EXPOSE 8000`).

### Exercise 2.2: Kết quả chạy container
```text
$ docker run -d --rm --name test-agent -p 8000:8000 my-agent:develop
$ curl -X POST "http://localhost:8000/ask?question=What+is+Docker"
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: So sánh kích thước image
Kết quả đo thực tế bằng `docker images | grep my-agent`:
- **Develop (`my-agent:develop`):** `1.67GB` (~1670 MB) — dùng base image `python:3.11` đầy đủ, single-stage.
- **Production (`my-agent:advanced`):** `240MB` — dùng **multi-stage build** (`builder` cài thư viện có `gcc`/`libpq-dev`, `runtime` chỉ copy `/root/.local` sang `python:3.11-slim` và chạy bằng non-root user `appuser`).
- **Chênh lệch:** Giảm **~1.43 GB (≈ 85.6%)** dung lượng so với bản develop.

### Exercise 2.4: Docker Compose stack & Nginx
**Sơ đồ kiến trúc stack (`02-docker/production/docker-compose.yml`):**
```text
Client ──(port 80/443)──► Nginx (reverse proxy / load balancer)
                              │
                              ▼ (network: internal)
                          Agent (FastAPI, port 8000, healthcheck /health)
                           ├──► Redis (redis:7-alpine, port 6379, session & rate limit)
                           └──► Qdrant (qdrant/qdrant:v1.9.0, port 6333, vector DB)
```
**Kết quả kiểm tra qua Nginx (`curl http://localhost/health`):**
```text
$ docker compose -p k5-day14-docker ps
k5-day14-docker-agent-1    Up 5 seconds (healthy)   8000/tcp
k5-day14-docker-nginx-1    Up 5 seconds             0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
k5-day14-docker-qdrant-1   Up 16 seconds (healthy)  6333-6334/tcp
k5-day14-docker-redis-1    Up 16 seconds (healthy)  6379/tcp

$ curl http://localhost/health
{"status":"ok","uptime_seconds":4.3,"version":"2.0.0","timestamp":"2026-11-26T08:29:22.560338"}
```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 lên Cloud
- **Platform:** Render (Docker Web Service, Root Directory `06-lab-complete` + Render Key Value Redis)
- **Public URL:** https://quanhda.onrender.com
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`
- **Kết quả kiểm tra nhanh:**
  - `GET /health` → `HTTP 200` (`{"status":"ok","environment":"production",...}`)
  - `GET /ready` → `HTTP 200` (`{"status":"ready","redis":"connected"}`)
  - `POST /ask` (không có `X-API-Key`) → `HTTP 401`
  - `POST /ask` (có `X-API-Key`) → `HTTP 200` (chi tiết xem [DEPLOYMENT.md](DEPLOYMENT.md) và `screenshots/test.png`)

**So sánh `railway.toml` vs `render.yaml`:**
- **`railway.toml`** (định dạng TOML): cấu hình gọn cho từng service đơn lẻ (`[build]` chỉ định `builder = "DOCKERFILE"`, `[deploy]` chỉ định `healthcheckPath = "/health"`, `restartPolicyType`). Các biến môi trường và Redis thường được thêm qua Railway Dashboard hoặc CLI (`railway variables set`).
- **`render.yaml`** (định dạng YAML — Blueprint / IaC): cho phép khai báo cả hạ tầng nhiều service cùng lúc (web service + Redis + envVars) trong một file; hỗ trợ tự sinh secret (`generateValue: true`) hoặc đánh dấu nhập tay bảo mật trên UI (`sync: false`) mà không hardcode secret vào Git.

### Exercise 3.3: Cloud Run Pipeline (`cloudbuild.yaml` & `service.yaml`)
- **`cloudbuild.yaml`** định nghĩa pipeline CI/CD 4 bước tuần tự khi push code lên `main`: **(1) `test`** chạy `pytest` trên `python:3.11-slim` → **(2) `build`** đóng gói Docker image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from`) → **(3) `push`** đẩy image lên Google Container Registry (`gcr.io`) → **(4) `deploy`** gọi `gcloud run deploy` triển khai lên Cloud Run vùng `asia-southeast1` với `min-instances=1` (tránh cold start), `max-instances=10`, RAM `512Mi`, CPU `1`, và inject secret từ Secret Manager (`--set-secrets`).
- **`service.yaml`** khai báo cấu hình service Cloud Run theo chuẩn Knative (IaC): thiết lập autoscaling (`minScale: 1`, `maxScale: 10`, `containerConcurrency: 80`), giới hạn tài nguyên (`limits: 1 CPU / 512Mi`), lấy `OPENAI_API_KEY` và `AGENT_API_KEY` qua `secretKeyRef`, cùng `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1–4.3: Test kết quả Auth & Rate Limiting (401 / 200 / 429)

**1. API Key Auth (`04-api-gateway/develop/app.py`):**
```text
# Không có header X-API-Key → 401 Unauthorized
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có header X-API-Key đúng → 200 OK
$ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -H "X-API-Key: secret-key-123" -d '{"question":"Hello"}'
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

**2. JWT Auth + Rate Limiting (`04-api-gateway/production/app.py`):**
Đăng nhập `POST /auth/token` với tài khoản `student` / `demo123` (giới hạn 10 request/phút) và gửi liên tiếp 12 request bằng `Authorization: Bearer <TOKEN_REDACTED>`:
```text
=== Request 1 ===  -> HTTP 200
=== Request 2 ===  -> HTTP 200
...
=== Request 10 === -> HTTP 200
=== Request 11 === -> HTTP 429
=== Request 12 === -> HTTP 429
```

### Exercise 4.4: Cost Guard Implementation
- **Vai trò khác với Rate Limit:** Rate limit giới hạn **tốc độ** gọi (số request/phút) để chống spam/DDoS, còn Cost Guard giới hạn **chi phí tiền** (token/USD theo ngày hoặc tháng) để tránh hóa đơn LLM API tăng đột biến khi câu hỏi dài hoặc bị lạm dụng.
- **Cách hoạt động (`04-api-gateway/production/cost_guard.py`):**
  1. Trước khi gọi LLM (`check_budget(username)`): kiểm tra chi phí tích lũy trong ngày của user (`daily_budget_usd = $1.0`) và toàn hệ thống (`global_daily_budget_usd = $10.0`). Nếu vượt ngưỡng thì chặn và trả về HTTP `402`.
  2. Sau khi LLM trả lời (`record_usage(username, input_tokens, output_tokens)`): tính chi phí theo đơn giá token input/output (`$0.00015 / 1K input`, `$0.0006 / 1K output`), cộng dồn vào bản ghi trong ngày và log cảnh báo khi đạt `80%` ngân sách (`warn_at_pct = 0.8`).
  3. Trong production thực tế (như Part 6), bộ đếm chi phí cần lưu trong **Redis** (hoặc DB dùng chung) thay vì dict trong RAM để đồng bộ giữa nhiều instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.5: Health/Readiness, Graceful Shutdown & Stateless Redis

**1. Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
- **`/health` (Liveness probe):** Kiểm tra tiến trình app còn sống hay bị treo. Kể cả khi Redis tạm mất kết nối, `/health` vẫn nên trả `200 OK` để platform không restart container một cách vô ích.
- **`/ready` (Readiness probe):** Kiểm tra service đã sẵn sàng nhận traffic chưa (ví dụ kết nối Redis thành công, không đang trong quá trình shutdown). Nếu Redis chết hoặc app đang tắt, `/ready` trả `503 Service Unavailable` để Load Balancer tạm ngưng gửi request mới vào instance đó.

**2. Tại sao state lưu trong RAM sẽ hỏng khi scale nhiều instance?**
- Khi chạy nhiều instance (ví dụ 3 replicas sau Nginx Load Balancer), các request trong cùng một phiên chat của người dùng sẽ được chia vòng tròn (round-robin) sang các instance khác nhau. Nếu lịch sử chat lưu trong RAM (`dict` nội bộ của từng process), instance B sẽ không thấy lịch sử ở instance A, gây mất ngữ cảnh hội thoại (hoặc sai lệch bộ đếm rate limit/cost guard).
- Giải pháp là thiết kế **Stateless**: đưa toàn bộ state dùng chung (session history, rate limit, cost usage) ra ngoài vào **Redis**.

**3. Kết quả chạy `test_stateless.py` với `--scale agent=3` (`05-scaling-reliability/production/`):**
```text
Session ID: 698c8a33-a13e-4787-ab26-56d894e644d8
Request 1: [instance-8a3640]
Request 2: [instance-5942eb]
Request 3: [instance-e7e94d]
Request 4: [instance-8a3640]
Request 5: [instance-5942eb]

Total requests: 5
Instances used: {'instance-5942eb', 'instance-8a3640', 'instance-e7e94d'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```
*(Giải thích: 5 request được Nginx điều phối sang cả 3 container agent khác nhau, nhưng toàn bộ 10 tin nhắn của session vẫn được đọc/ghi đầy đủ nhờ lưu tập trung trong Redis).*

---

## Part 6: Final Project (`06-lab-complete/`) — Checklist Deliverable

Kết quả chạy `python3 check_production_ready.py` (đầy đủ, có Docker) trong thư mục `06-lab-complete/`:

```text
========================================================================
📋 Checklist Deliverable
  ✅ Dockerfile (multi-stage, < 500 MB)
  ✅ docker-compose.yml (agent + redis)
  ✅ .dockerignore
  ✅ Health check endpoint (GET /health)
  ✅ Readiness endpoint (GET /ready)
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Config từ environment variables
  ✅ Structured logging
  ✅ Graceful shutdown
  ✅ Public URL ready (Railway / Render config)
------------------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
========================================================================
```

---

## AI Usage Log

| Mục / Bước | Công cụ AI sử dụng | Nội dung hỗ trợ | Kiểm chứng bởi học viên |
| :--- | :--- | :--- | :--- |
| Part 1–5 (Setup, Docker, Auth, Scaling) | Antigravity AI Assistant | Hướng dẫn từng bước trên WSL2, sửa lỗi quyền Docker socket, tổng hợp câu trả lời vào `MISSION_ANSWERS.md`. | Tự chạy toàn bộ lệnh `curl`, `docker build`, `docker compose`, `test_stateless.py` và đối chiếu kết quả thực tế. |
| Part 6 (`06-lab-complete/`) | Antigravity AI Assistant | Triển khai các `TODO` (config, auth, Redis rate limiter, cost guard, JSON logging, graceful shutdown, multi-stage Dockerfile, compose, deploy config). | Chạy `python3 check_production_ready.py` đạt `PASS 12/12` (43/43 checks). |
| Part 3 (Render Deployment) | Antigravity AI Assistant | Hướng dẫn cấu hình Render Web Service + Redis, kiểm tra endpoint public và viết `DEPLOYMENT.md`. | Tự tạo service & secret trên Render, kiểm tra live URL `https://quanhda.onrender.com`. |
| Part 7 (Benchmark & Observability) | Antigravity AI Assistant | Chạy load test, eval v1/v2, sửa `KNOWLEDGE_BASE` đạt 100%, sửa lỗi `Dockerfile` mẫu ở `benchmark-observability/production/`, chạy Locust scaling + alerts và điền `BENCHMARK_REPORT.md`. | Đối chiếu số liệu trong `BENCHMARK_REPORT.md` khớp 100% với file JSON/CSV trong `reports/`, `benchmark-results/` và 4 ảnh trong `screenshots/`. |
