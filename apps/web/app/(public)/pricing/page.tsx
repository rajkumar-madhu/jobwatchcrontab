import { redirect } from "next/navigation";

// R71: /pricing used to 404 — the plans live on the landing page. Buyers type the URL directly.
export const metadata = { title: "Pricing · WeCrew JobWatch" };
export default function Pricing() {
  redirect("/welcome#pricing");
}
