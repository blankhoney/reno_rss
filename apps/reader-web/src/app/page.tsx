export default function HomePage() {
  return (
    <main className="shell">
      <aside className="sidebar">
        <strong>AI Reader</strong>
        <nav>
          <a href="#unread">未读</a>
          <a href="#saved">收藏</a>
          <a href="#later">稍后读</a>
        </nav>
      </aside>
      <section className="listPane">
        <h1>阅读工作台</h1>
        <p>文章列表会在 API 接通后显示在这里。</p>
      </section>
      <article className="readerPane">
        <h2>站内阅读</h2>
        <p>选择文章后，这里展示正文、分数和当前文章 Agent。</p>
      </article>
    </main>
  );
}
