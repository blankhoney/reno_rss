"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

const ITEMS = [
  { id: "home", label: "情报", href: "/?module=home&sort=default&lang=zh" },
  { id: "all", label: "最新", href: "/?module=all&sort=default&lang=zh" },
  { id: "starred", label: "候选", href: "/?module=starred&sort=default&lang=zh" },
  { id: "review", label: "复习", href: "/?module=review&sort=default&lang=zh" },
  { id: "project", label: "已立项", href: "/?module=project&sort=default&lang=zh" },
] as const;

export function MobileBottomNav() {
  const pathname = usePathname();
  const search = useSearchParams();
  const moduleId = search.get("module") || (pathname?.startsWith("/read") ? "all" : "home");

  return (
    <nav className="mobileBottomNav" aria-label="移动主导航">
      {ITEMS.map((item) => {
        const active = moduleId === item.id || (item.id === "home" && moduleId === "intelligence");
        return (
          <Link
            key={item.id}
            href={item.href}
            className={active ? "mobileBottomNavItem is-active" : "mobileBottomNavItem"}
            prefetch={false}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
