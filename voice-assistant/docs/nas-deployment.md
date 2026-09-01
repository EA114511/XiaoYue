# 小玥 AI 语音助手 — 绿联云 NAS 部署指南

> 将 FastAPI 后端部署到绿联云 NAS 4800 的 Docker 容器中。

---

## NAS 型号

绿联云 NAS 4800（或其他支持 Docker 的绿联云型号）

## 前提条件

| 项目 | 要求 |
|------|------|
| Docker | 已安装并运行 |
| 内存 | ≥ 4GB 可用（Whisper 模型需 ~1GB） |
| 存储 | ≥ 10GB 可用空间 |
| 网络 | NAS 与手机在同一局域网 |

---

## 部署步骤

### 1. 打包项目

在 Windows 本地打包必要文件：

```bash
cd voice-assistant
tar -czf voice-assistant-nas.tar.gz backend/ docker-compose.yml
```

或使用 7-Zip / WinRAR 打包为 zip。

### 2. 上传到 NAS

通过以下任一方式上传 `voice-assistant-nas.tar.gz`：

- **绿联云 App**：文件管理 → 上传
- **Samba**：`\\nas-ip\共享文件夹`
- **FTP/SFTP**：使用 FileZilla 等工具

上传到 NAS 后解压：

```bash
cd /path/to/voice-assistant
tar -xzf voice-assistant-nas.tar.gz
```

### 3. 创建环境配置

在 NAS 上创建 `backend/.env`：

```bash
cd voice-assistant/backend
nano .env
```

粘贴以下内容（根据实际情况修改）：

```ini
# ========== 服务器配置 ==========
HOST=0.0.0.0
PORT=8000
DEBUG=false

# 允许的来源（包含 Android App 和局域网）
ALLOWED_ORIGINS=http://localhost,http://192.168.5.5,capacitor://localhost,http://localhost:3000

# ========== 安全配置（必须修改！）==========
# 生成随机 Token：python -c "import secrets; print(secrets.token_urlsafe(32))"
API_TOKEN=your-strong-api-token-here

# 生成随机 Key：python -c "import secrets; print(secrets.token_hex(32))"
CRYPTO_KEY=your-random-32-byte-hex-key-here

# ========== LLM Provider 配置 ==========
# 智谱 GLM（默认）
OPENAI_API_KEY=your-glm-api-key
OPENAI_API_BASE=https://open.bigmodel.cn/api/paas/v4
OPENAI_MODEL=glm-4.5

# ========== 语音识别配置 ==========
WHISPER_MODEL_SIZE=base
ASR_DEFAULT_LANGUAGE=zh
VAD_SENSITIVITY=2

# ========== 数据库配置 ==========
DATABASE_URL=sqlite:///./data/voice_assistant.db
```

**重要**：`API_TOKEN` 和 `CRYPTO_KEY` 必须设置为强随机值！

### 4. 启动服务

```bash
cd voice-assistant
docker-compose up -d
```

### 5. 验证部署

```bash
# 查看容器状态
docker-compose ps

# 查看日志
docker-compose logs -f backend

# 健康检查
curl http://localhost:8000/api/v1/health/status
```

预期返回：

```json
{"status":"healthy","service":"voice-assistant","version":"1.0.0",...}
```

---

## 目录结构

```
voice-assistant/
├── backend/
│   ├── .env              # 环境变量（不要提交到 Git）
│   ├── data/             # 持久化数据（SQLite、Provider 配置）
│   ├── logs/             # 日志目录
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── docker-compose.yml
└── ...
```

---

## 常用命令

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 查看日志
docker-compose logs -f backend

# 重启
docker-compose restart backend

# 更新代码后重新构建
docker-compose up -d --build

# 进入容器调试
docker-compose exec backend bash
```

---

## 网络配置

### 局域网访问

NAS 的局域网 IP 通常是 `192.168.x.x` 或 `10.x.x.x`。

在路由器中查看 NAS 的 IP 地址，或在 NAS 上执行：

```bash
ip addr show | grep inet
```

假设 NAS IP 为 `192.168.5.5`，则：

- 后端 API：`http://192.168.5.5:8000`
- API 文档：`http://192.168.5.5:8000/docs`

### 防火墙设置

确保 NAS 防火墙允许以下端口：

| 端口 | 用途 |
|------|------|
| 8000 | 后端 API |
| 3000 | 前端 Web（可选） |

---

## 性能优化

### 模型选择

绿联云 NAS 4800 性能有限，建议：

```ini
# .env 中修改
WHISPER_MODEL_SIZE=base   # 平衡性能与准确率
# 或
WHISPER_MODEL_SIZE=tiny   # 最快，准确率较低
```

模型大小对比：

| 模型 | 内存占用 | 速度 | 准确率 |
|------|---------|------|--------|
| tiny | ~500MB | 最快 | 一般 |
| base | ~1GB | 快 | 较好 |
| small | ~2GB | 中等 | 好 |

### 内存限制

`docker-compose.yml` 中已配置内存限制：

```yaml
deploy:
  resources:
    limits:
      memory: 4G
```

如 NAS 内存不足，可降低为 `2G`。

---

## 数据备份

### 备份内容

```
voice-assistant/backend/data/
├── voice_assistant.db      # 对话历史、用户数据
├── llm_providers.json      # LLM Provider 配置
├── voice_providers.json    # 语音 Provider 配置
├── agent_configs.json      # 智能体配置
└── mcp_servers.json        # MCP 服务器配置
```

### 备份命令

```bash
# 备份数据卷
docker run --rm -v voice-assistant-backend-data:/data -v $(pwd):/backup alpine tar czf /backup/voice-assistant-backup-$(date +%Y%m%d).tar.gz -C /data .
```

建议将备份纳入 NAS 定时任务。

---

## 故障排查

### Q1: 容器启动失败？

```bash
# 查看详细日志
docker-compose logs backend

# 检查端口占用
netstat -tlnp | grep 8000
```

### Q2: 无法访问后端？

```bash
# 检查容器是否运行
docker ps

# 检查防火墙
sudo ufw status
# 或
sudo iptables -L
```

### Q3: ASR 识别很慢？

- 降低 Whisper 模型：`WHISPER_MODEL_SIZE=tiny`
- 检查 NAS CPU 使用率：`docker stats`

### Q4: 数据库损坏？

```bash
# 停止服务
docker-compose down

# 删除数据库文件（注意：会丢失历史记录！）
rm backend/data/voice_assistant.db

# 重新启动
docker-compose up -d
```

---

## 远程访问（可选）

如需在外网访问 NAS 后端，推荐使用 **Tailscale**：

1. NAS 安装 Tailscale（应用商店或 Docker）
2. 手机安装 Tailscale
3. 登录同一账号
4. 使用 Tailscale 虚拟 IP（如 `100.x.x.x`）访问

详细配置请参考 [Tailscale 官方文档](https://tailscale.com/kb/)。

---

> 绿联云 NAS 官方 Docker 文档：[UGREEN NAS Docker](https://www.ugnas.com/)
