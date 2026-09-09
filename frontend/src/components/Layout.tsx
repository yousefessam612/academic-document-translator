import { NavLink, Link } from 'react-router-dom'
import type { ReactNode } from 'react'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '📊' },
  { to: '/upload', label: 'Upload', icon: '📤' },
  { to: '/documents', label: 'Documents', icon: '📄' },
  { to: '/terminology', label: 'Terminology', icon: '📚' },
  { to: '/memory', label: 'Translation Memory', icon: '🧠' },
  { to: '/completed', label: 'Completed', icon: '✅' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex">
      <aside className="w-60 shrink-0 bg-slate-900 text-slate-200 flex flex-col">
        <div className="px-5 py-5 border-b border-slate-800">
          <Link to="/" className="block">
            <div className="text-lg font-bold text-white leading-tight">Academic Translator</div>
            <div className="text-xs text-slate-400 mt-1">English → Arabic documents</div>
          </Link>
        </div>
        <nav className="flex-1 py-4">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white border-r-2 border-emerald-400'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <span>{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 text-xs text-slate-500 border-t border-slate-800">
          v1.0 — AgentRouter powered
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="max-w-6xl mx-auto px-8 py-8">{children}</div>
      </main>
    </div>
  )
}
