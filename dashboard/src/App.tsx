import { Route, Routes } from "react-router-dom";
import { Landing } from "@/routes/Landing";
import { SignIn } from "@/routes/SignIn";
import { Setup } from "@/routes/Setup";
import { AppLayout } from "@/routes/AppLayout";
import { Overview } from "@/routes/Overview";
import { Sent } from "@/routes/Sent";
import { Waiting } from "@/routes/Waiting";
import { CantSend } from "@/routes/CantSend";
import { Preferred } from "@/routes/Preferred";
import { ResumePage } from "@/routes/ResumePage";
import { ProfilePage } from "@/routes/ProfilePage";
import { SettingsPage } from "@/routes/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/signin" element={<SignIn />} />
      <Route path="/setup" element={<Setup />} />

      <Route path="/app" element={<AppLayout />}>
        <Route index element={<Overview />} />
        <Route path="sent" element={<Sent />} />
        <Route path="waiting" element={<Waiting />} />
        <Route path="preferred" element={<Preferred />} />
        <Route path="failed" element={<CantSend />} />
        <Route path="resume" element={<ResumePage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route
        path="*"
        element={
          <div className="grid min-h-screen place-items-center bg-bg px-6 text-center">
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">
                404
              </p>
              <h1 className="mt-2 font-display text-[24px] font-semibold">
                That page is not in the log.
              </h1>
              <a
                href="/"
                className="mt-4 inline-block text-[13px] text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink"
              >
                Back to the landing page
              </a>
            </div>
          </div>
        }
      />
    </Routes>
  );
}
