import { useEffect, useState } from "react";
import { Link, Route, Routes, useNavigate } from "react-router-dom";
import { api, setToken } from "./api";
import Home from "./pages/Home";
import Research from "./pages/Research";
import Entity from "./pages/Entity";
import { Login, Register } from "./pages/Auth";
import Account from "./pages/Account";

export default function App() {
  const [usage, setUsage] = useState<any>(null);
  const nav = useNavigate();
  const refresh = () => api("/usage").then(setUsage).catch(() => setUsage(null));
  useEffect(() => { refresh(); }, []);

  return (
    <>
      <header>
        <Link to="/" className="logo">OpenIntel</Link>
        <nav>
          {usage && usage.limit > 0 && <span className="muted">{usage.used}/{usage.limit} searches</span>}
          {usage?.email ? (
            <>
              <Link to="/account">Account</Link>
              <a href="#" onClick={(e) => { e.preventDefault(); setToken(null); refresh(); nav("/"); }}>Sign out</a>
            </>
          ) : (
            <>
              <Link to="/login">Sign in</Link>
              <Link to="/register">Register</Link>
            </>
          )}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Home onSearch={refresh} signedIn={!!usage?.email} />} />
          <Route path="/research/:jobId" element={<Research />} />
          <Route path="/entities/:id" element={<Entity signedIn={!!usage?.email} />} />
          <Route path="/login" element={<Login onAuth={refresh} />} />
          <Route path="/register" element={<Register onAuth={refresh} />} />
          <Route path="/account" element={<Account />} />
        </Routes>
      </main>
    </>
  );
}
