import { Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import { About } from "./pages/About";
import { InventoryTabs } from "./components/layout/InventoryTabs";
import { AcceptanceDetail } from "./pages/AcceptanceDetail";
import { AcceptanceQueue } from "./pages/AcceptanceQueue";
import { AssetDetail } from "./pages/AssetDetail";
import { Assets } from "./pages/Assets";
import { CaseStudy } from "./pages/CaseStudy";
import { DemoLauncher } from "./pages/DemoLauncher";
import { IncidentQueue } from "./pages/IncidentQueue";
import { IncidentWorkspace } from "./pages/IncidentWorkspace";
import { Infrastructure } from "./pages/Infrastructure";
import { NotFound } from "./pages/NotFound";
import { Overview } from "./pages/Operations";
import { Report } from "./pages/Report";
import { Returns } from "./pages/Returns";
import { Runbooks } from "./pages/Runbooks";
import { SettingsPage } from "./pages/Settings";
import { Spares } from "./pages/Spares";

export function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/operations" element={<RedirectHome />} />
        <Route path="/about" element={<About />} />
        <Route path="/incidents" element={<IncidentQueue />} />
        <Route path="/incidents/:id" element={<IncidentWorkspace />} />
        <Route path="/acceptance" element={<AcceptanceQueue />} />
        <Route path="/acceptance/:id" element={<AcceptanceDetail />} />
        <Route path="/acceptance/runs/:runId/report" element={<Report />} />
        <Route path="/infrastructure" element={<Infrastructure />} />
        <Route element={<InventoryLayout />}>
          <Route path="/assets" element={<Assets />} />
          <Route path="/spares" element={<Spares />} />
          <Route path="/returns" element={<Returns />} />
        </Route>
        <Route path="/assets/:id" element={<AssetDetail />} />
        <Route path="/runbooks" element={<Runbooks />} />
        <Route path="/runbooks/:slug" element={<Runbooks />} />
        <Route path="/projects/:slug" element={<CaseStudy />} />
        <Route path="/demo" element={<DemoLauncher />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Shell>
  );
}

function RedirectHome() {
  const loc = useLocation();
  return <Navigate to={{ pathname: "/", search: loc.search }} replace />;
}

function InventoryLayout() {
  return <><InventoryTabs /><Outlet /></>;
}
