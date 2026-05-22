import { OnboardingWizard } from "./onboarding-wizard";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function OnboardingPage() {
  await requireSession();
  return <OnboardingWizard />;
}
