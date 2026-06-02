import type { DemoAccessConfig } from "@/lib/demo/access";

const GITHUB_URL = "https://github.com/blankhoney/reno_rss";

export function DemoLanding({ config }: { config: DemoAccessConfig }) {
  const ready = config.enabled && Boolean(config.username) && Boolean(config.password);

  return (
    <main className="demoLanding">
      <section className="demoHero" aria-labelledby="demo-title">
        <p className="demoEyebrow">Resume Demo</p>
        <h1 id="demo-title">AI Reader</h1>
        <p className="demoLead">
          一个面向中文用户的 RSS 智能阅读工作台，支持文章评分、中文摘要、专注阅读、实时重评和文章问答。
        </p>
        <div className="demoActions">
          <form action="/api/demo-login" method="post">
            <button className="demoPrimaryButton" type="submit" disabled={!ready}>
              以游客身份进入
            </button>
          </form>
          <a className="demoSecondaryButton" href={GITHUB_URL} target="_blank" rel="noreferrer noopener">
            查看 GitHub 源码
          </a>
        </div>
        <div className="demoCredentials" aria-label="游客登录信息">
          <p>
            <span>用户名</span>
            <strong>{config.username || "demo"}</strong>
          </p>
          <p>
            <span>密码</span>
            <strong>{config.password || "Demo 暂未配置"}</strong>
          </p>
        </div>
        {!ready ? (
          <p className="demoWarning">Demo 暂未配置完整游客凭据，请稍后再试或查看 GitHub 源码。</p>
        ) : (
          <p className="demoHint">
            游客账号仅用于体验 staging AI Reader，不用于生产数据；页面操作可能被其他访客共享。
          </p>
        )}
      </section>
      <section className="demoFeatureGrid" aria-label="可体验功能">
        <article>
          <h2>评分与摘要</h2>
          <p>按技术、商业、趋势等维度筛选文章，重评当前列表并生成中文摘要。</p>
        </article>
        <article>
          <h2>专注阅读</h2>
          <p>在站内阅读 RSS 正文，必要时刷新源站全文，并保留外链原文入口。</p>
        </article>
        <article>
          <h2>文章问答</h2>
          <p>基于当前文章片段、摘要和评分信息进行中文问答，帮助快速判断信息价值。</p>
        </article>
      </section>
    </main>
  );
}
