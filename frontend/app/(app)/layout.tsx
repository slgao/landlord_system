"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/api";
import { Sidebar } from "@/components/nav";
import { CommandSearch } from "@/components/command-search";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [router]);

  return (
    <div className="flex md:h-screen md:overflow-hidden">
      {/* Twenty-one nav links stand between the top of the page and its
          content, so a keyboard user pressed Tab two dozen times to reach
          the first control. Hidden until focused, as a skip link should be. */}
      <a href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50
          focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm
          focus:text-primary-foreground">
        Skip to content
      </a>
      <Sidebar />
      <CommandSearch />
      {/* pt-14 on mobile clears the fixed top bar */}
      <main id="main" tabIndex={-1}
        className="flex-1 min-w-0 md:overflow-y-auto p-4 md:p-6 pt-[4.5rem] md:pt-6">
        {children}
      </main>
    </div>
  );
}
