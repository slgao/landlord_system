"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/api";
import { Sidebar } from "@/components/nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  useEffect(() => {
    if (!isAuthenticated()) router.replace("/login");
  }, [router]);

  return (
    <div className="flex md:h-screen md:overflow-hidden">
      <Sidebar />
      {/* pt-14 on mobile clears the fixed top bar */}
      <main className="flex-1 md:overflow-y-auto p-4 md:p-6 pt-[4.5rem] md:pt-6">{children}</main>
    </div>
  );
}
