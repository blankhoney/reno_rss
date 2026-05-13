# Runbook: VPS Agent Diagnostics

Use this when the local coding session cannot directly inspect VPS-only state
such as real `.env`, Docker daemon, Caddy TLS state, or running containers.

## AI Reader Staging Diagnostic Prompt

Copy this whole prompt to the VPS agent.

```text
你现在在 VPS 上诊断 my_rss 项目。请只读检查，不要修改文件，不要重启服务，不要部署，不要执行 destructive command，不要打印 .env 原文、密码、token、cookie 或 API key。

目标：诊断 AI Reader staging 是否部署到位，并定位 https://staging-ai-reader.blankhoney.xyz 的 TLS / Caddy / reader-web 问题。

项目目录优先使用：
/root/opt/myrss/app

请执行并总结以下检查。

1. 仓库状态

cd /root/opt/myrss/app
pwd
git status --short --branch
git log --oneline -n 8
git branch -vv

重点确认：
- 当前是否在 feat/ai-reader-web。
- HEAD 是否包含 8fa227e feat(infra): route reader web。
- HEAD 是否包含 e23b103 feat(reader-web): add article agent panel。

2. Caddyfile 宿主机与容器内挂载是否一致

echo "HOST_CADDYFILE"
grep -nE 'staging-ai-reader|ai-reader|reader-web' infra/caddy/Caddyfile || true
wc -c infra/caddy/Caddyfile
sha256sum infra/caddy/Caddyfile

echo "CONTAINER_CADDYFILE"
docker exec myrss-edge-caddy-1 sh -c "grep -nE 'staging-ai-reader|ai-reader|reader-web' /etc/caddy/Caddyfile || true"
docker exec myrss-edge-caddy-1 sh -c "wc -c /etc/caddy/Caddyfile && sha256sum /etc/caddy/Caddyfile"

重点判断：
- 宿主机是否包含 staging-ai-reader。
- 容器内是否包含 staging-ai-reader。
- 两边文件大小和 sha256 是否一致。

3. Caddy 配置有效性与已适配配置

docker exec myrss-edge-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec myrss-edge-caddy-1 caddy adapt --config /etc/caddy/Caddyfile --pretty | grep -nE 'staging-ai-reader|ai-reader|reader-web' || true
docker logs --tail=200 myrss-edge-caddy-1 | grep -E 'staging-ai-reader|ai-reader|certificate|tls|error|automatic TLS|load complete|config is unchanged' || true

重点判断：
- validate 是否成功。
- adapted JSON 是否包含 staging-ai-reader。
- 日志是否显示 Caddy 已加载新配置。
- 日志是否出现 staging-ai-reader 证书申请、TLS 或 SNI 错误。

4. Compose staging 展开配置

不要打印 .env 值。只执行：

docker compose \
  --env-file .env \
  -f infra/compose/docker-compose.base.yml \
  -f infra/compose/docker-compose.staging.yml \
  config >/tmp/myrss-staging.yml

grep -nE 'reader-web|reader-web-staging|READER_MINIFLUX_USER_ID|WEB_SEARCH_PROVIDER|MINIMAX_MODEL' /tmp/myrss-staging.yml || true

重点判断：
- 是否存在 reader-web 服务。
- 是否存在 reader-web-staging 网络别名。
- 是否存在关键变量名。不要输出真实 secret。

5. 容器状态与日志

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'reader-web|caddy|authelia|miniflux|postgres' || true
docker logs --tail=120 myrss-staging-reader-web-1 2>&1 || true

重点判断：
- myrss-staging-reader-web-1 是否存在并 Up。
- reader-web 是否有启动错误、缺失环境变量、Next.js 启动失败。

6. DNS 与 TLS 对比

getent hosts staging-ai-reader.blankhoney.xyz || true
curl -vkI --resolve staging-ai-reader.blankhoney.xyz:443:127.0.0.1 https://staging-ai-reader.blankhoney.xyz 2>&1 | tail -80
curl -vkI https://staging-ai-reader.blankhoney.xyz 2>&1 | tail -80
curl -vkI https://staging-reader.blankhoney.xyz 2>&1 | tail -40

重点判断：
- 本机 Caddy 是否能响应 staging-ai-reader。
- 公网 DNS 访问是否打到同一台机器。
- staging-reader 正常而 staging-ai-reader 失败时，优先怀疑 Caddy 未加载新站点或证书未申请。

请按以下格式返回。不要贴长日志全文，只贴关键行。

【结论】
- 一句话说明最可能原因。

【关键证据】
- 当前 git 分支和 HEAD：
- 是否包含 8fa227e / e23b103：
- 宿主机 Caddyfile 是否包含 staging-ai-reader：
- 容器内 Caddyfile 是否包含 staging-ai-reader：
- 宿主机和容器内 Caddyfile sha256 是否一致：
- Caddy validate 结果：
- Caddy adapted JSON 是否包含 staging-ai-reader：
- Caddy logs 是否出现 staging-ai-reader 证书/加载记录：
- compose config 是否包含 reader-web 和 reader-web-staging：
- reader-web 容器是否存在：
- reader-web 日志关键错误：
- DNS 指向：
- curl --resolve 结果：
- 公网 curl staging-ai-reader 结果：
- curl staging-reader 是否正常：

【建议下一步】
- 给出 1-3 条最小操作建议。
- 如果需要改动，请只建议，不要执行。
```

## Safety Notes

- If any secret was pasted into chat or logs, rotate it before production use.
- Prefer staging verification on `feat/ai-reader-web` before merging to `main`.
- Use `curl --resolve ...:127.0.0.1` to separate local Caddy state from DNS or multi-IP routing.
