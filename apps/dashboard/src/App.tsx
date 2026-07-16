import type { ReactNode } from "react";
import { useEffect } from "react";
import { Link, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./lib/useAuth";
import { userAvatarUrl } from "./lib/discord";
import { loginUrl } from "./lib/api";
import { DirtyProvider, useDirty } from "./lib/dirty";
import { Login } from "./pages/Login";
import { Guilds } from "./pages/Guilds";
import { GuildSettings } from "./pages/GuildSettings";
import { SetupWizard } from "./pages/SetupWizard";
import { Landing } from "./pages/Landing";
import { DocsCommands } from "./pages/DocsCommands";
import { NotFound } from "./pages/NotFound";
import { Skeleton } from "./components/Skeleton";
import "./App.css";

function Header() {
  const { me, loading, logout } = useAuth();
  const navigate = useNavigate();
  const { guardNavigation } = useDirty();
  const avatar = me ? userAvatarUrl(me.user) : null;

  function goHome() {
    guardNavigation(() => navigate("/"));
  }

  return (
    <header className="app-header">
      <button className="app-title app-title--link" onClick={goHome}>
        kidney bot
      </button>
      <div className="app-user">
        <Link className="button button--link" to="/docs/commands">
          Docs
        </Link>
        {!loading && me && (
          <>
            {avatar && <img className="user-avatar" src={avatar} alt="" />}
            <span>{me.user.username}</span>
            <button className="button button--link" onClick={() => void logout()}>
              Log out
            </button>
          </>
        )}
        {!loading && !me && (
          <a className="button" href={loginUrl()}>
            Login
          </a>
        )}
      </div>
    </header>
  );
}

/** Prompts before closing/reloading the tab while a form has unsaved changes. */
function UnsavedChangesGuard() {
  const { dirty } = useDirty();

  useEffect(() => {
    function handler(e: BeforeUnloadEvent) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    }
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  return null;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <p>Loading…</p>;
  if (!me) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function Home() {
  const { me, loading } = useAuth();
  if (loading) return <Skeleton rows={4} />;
  return me ? <Guilds /> : <Landing />;
}

function App() {
  const { me, loading } = useAuth();

  return (
    <DirtyProvider>
      <div className="app">
        <Header />
        <UnsavedChangesGuard />
        <main className="app-main">
          <Routes>
            <Route
              path="/login"
              element={loading ? <p>Loading…</p> : me ? <Navigate to="/" replace /> : <Login />}
            />
            <Route path="/" element={<Home />} />
            <Route path="/docs/commands" element={<DocsCommands />} />
            <Route
              path="/guilds/:guildId/setup"
              element={
                <RequireAuth>
                  <SetupWizard />
                </RequireAuth>
              }
            />
            <Route
              path="/guilds/:guildId"
              element={
                <RequireAuth>
                  <GuildSettings />
                </RequireAuth>
              }
            />
            <Route
              path="/guilds/:guildId/settings/:domainKey"
              element={
                <RequireAuth>
                  <GuildSettings />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </div>
    </DirtyProvider>
  );
}

export default App;
