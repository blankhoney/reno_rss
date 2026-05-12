import type { Article } from "@/lib/articles/types";
import { ScoreBadge } from "./ScoreBadge";

type ArticleListProps = {
  articles: Article[];
  currentModule: string;
  selectedArticleId: number | null;
};

function listHref(currentModule: string, articleId: number): string {
  const qs = new URLSearchParams({ module: currentModule, article: String(articleId) });
  return `?${qs.toString()}`;
}

export function ArticleList({ articles, currentModule, selectedArticleId }: ArticleListProps) {
  return (
    <section className="articleListPane" aria-label="文章列表">
      <header className="articleListHeader">
        <h1 className="articleListTitle">阅读工作台</h1>
        <label className="articleSortLabel">
          <span className="visuallyHidden">排序</span>
          <select className="articleSortSelect" defaultValue="relevance" aria-label="排序方式">
            <option value="relevance">按相关性</option>
            <option value="time">按时间</option>
            <option value="score">按总分</option>
          </select>
        </label>
      </header>
      <ul className="articleList">
        {articles.map((article) => {
          const score = article.score;
          const isActive = selectedArticleId != null && selectedArticleId === article.id;
          return (
            <li key={article.id}>
              <a
                className={`articleCard${isActive ? " articleCardActive" : ""}`}
                href={listHref(currentModule, article.id)}
                aria-current={isActive ? "true" : undefined}
              >
                <div className="articleCardMeta">
                  <span className="articleFeed">{article.feedTitle}</span>
                  {article.categoryTitle ? (
                    <span className="articleCategory">{article.categoryTitle}</span>
                  ) : null}
                </div>
                <div className="articleCardTitle">{article.title}</div>
                <div className="articleCardScores">
                  <ScoreBadge label="总分" value={score?.overall ?? null} />
                  <ScoreBadge
                    label="技术"
                    value={score?.dimensions.technical_value ?? null}
                  />
                  <ScoreBadge
                    label="商业"
                    value={score?.dimensions.business_value ?? null}
                  />
                </div>
              </a>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
