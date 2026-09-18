import { useEffect, useState, type FormEvent } from 'react'
import type { User } from '../api/types'
import { login, register } from '../api/client'

type Mode = 'login' | 'register'

interface Props {
  onClose: () => void
  onAuthed: (user: User) => void
}

export function AuthModal({ onClose, onAuthed }: Props) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [nome, setNome] = useState('')
  const [codigo, setCodigo] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Esc fecha o modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const isReg = mode === 'register'

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      if (isReg) await register(email.trim(), senha, nome.trim() || undefined, codigo.trim())
      const user = await login(email.trim(), senha)
      onAuthed(user)
    } catch (err) {
      setError(friendly((err as Error).message))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={isReg ? 'Criar conta' : 'Entrar'}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-h">
          <h2>{isReg ? 'Criar conta' : 'Entrar'}</h2>
          <button className="modal-x" type="button" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </div>
        <p className="modal-sub">IncorpoData · acesso para construtoras e incorporadoras.</p>

        <form className="auth-form" onSubmit={submit}>
          {isReg && (
            <label>
              Nome (opcional)
              <input
                className="inp"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                autoComplete="name"
              />
            </label>
          )}
          <label>
            E-mail
            <input
              className="inp"
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
            />
          </label>
          <label>
            Senha
            <input
              className="inp"
              type="password"
              required
              minLength={8}
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              autoComplete={isReg ? 'new-password' : 'current-password'}
            />
          </label>
          {isReg && <p className="auth-hint">Mínimo 8 caracteres.</p>}
          {isReg && (
            <label>
              Código de convite
              <input
                className="inp"
                required
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                autoComplete="off"
                placeholder="recebido do IncorpoData"
              />
            </label>
          )}
          {error && <p className="auth-err">{error}</p>}
          <button className="btn" type="submit" disabled={busy}>
            {busy ? '…' : isReg ? 'Criar conta e entrar' : 'Entrar'}
          </button>
        </form>

        <p className="auth-switch">
          {isReg ? 'Já tem conta?' : 'Não tem conta?'}{' '}
          <button
            type="button"
            onClick={() => {
              setMode(isReg ? 'login' : 'register')
              setError(null)
            }}
          >
            {isReg ? 'Entrar' : 'Criar conta'}
          </button>
        </p>
      </div>
    </div>
  )
}

// Traduz o `detail` da API para mensagem amigável (sem revelar se o e-mail existe).
function friendly(msg: string): string {
  const m = (msg || '').toLowerCase()
  if (m.includes('credenciais')) return 'E-mail ou senha incorretos.'
  if (m.includes('convite') || m.includes('desabilitado') || m.includes('403'))
    return 'Código de convite inválido ou ausente. Fale com o IncorpoData para receber um.'
  if (m.includes('cadastrado') || m.includes('409')) return 'E-mail já cadastrado. Tente entrar.'
  if (m.includes('muitas tentativas') || m.includes('429'))
    return 'Muitas tentativas. Aguarde alguns minutos.'
  if (m.includes('422')) return 'Verifique o e-mail e a senha (mínimo 8 caracteres).'
  return msg || 'Não foi possível concluir. Tente de novo.'
}
