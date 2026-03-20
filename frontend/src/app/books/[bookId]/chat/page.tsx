'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter, useParams } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import { useI18n } from '@/lib/i18n'
import { 
  ArrowLeft, 
  BookOpen, 
  Cpu, 
  Send, 
  Loader2, 
  Quote, 
  Hash, 
  MessageSquare,
  Sparkles
} from 'lucide-react'
import { listBooks, bookQA, playGroundStream } from '@/lib/api'

type Mode = 'rag' | 'agent'
type Message = { role: 'user' | 'assistant', content: string, sources?: any[] }

export default function ChatPage() {
  const { t } = useI18n()
  const params = useParams()
  const router = useRouter()
  const bookId = params.bookId as string

  const [mode, setMode] = useState<Mode>('rag')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [book, setBook] = useState<any>(null)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    listBooks().then(books => {
      const b = books.find(b => String(b.book_id) === String(bookId))
      setBook(b)
    }).catch(console.error)
  }, [bookId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const userMsg = input.trim()
    setInput('')
    
    const newMessages: Message[] = [...messages, { role: 'user', content: userMsg }]
    setMessages(newMessages)
    setLoading(true)

    // Add loading placeholder for assistant message
    setMessages(prev => [...prev, { role: 'assistant', content: '__LOADING__' }])

    if (mode === 'rag') {
      try {
        const res = await bookQA(bookId, userMsg)
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: res.answer, sources: res.sources }
          return next
        })
      } catch (e: any) {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1] = { role: 'assistant', content: t('chat.error.answerFailed', { message: e.message }) }
          return next
        })
      } finally {
        setLoading(false)
      }
    } else {
      if (!book?.skill_id) {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1].content = t('chat.error.agentNoSkill')
          return next
        })
        setLoading(false)
        return
      }
      
      try {
        let content = ''
        const history = messages.map(m => ({ role: m.role, content: m.content }))
        
        for await (const chunk of playGroundStream(book.skill_id, userMsg, history)) {
          content += chunk
          setMessages(prev => {
            const next = [...prev]
            next[next.length - 1].content = content
            return next
          })
        }
      } catch (e: any) {
        setMessages(prev => {
          const next = [...prev]
          next[next.length - 1].content += `\n\n${t('chat.error.refineException', { message: e.message })}`
          return next
        })
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <div style={{ display: 'flex', height: '100vh', background: 'var(--bg)' }}>
      
      {/* Sidebar */}
      <aside style={{ 
        width: '320px', 
        borderRight: '1px solid var(--border)', 
        display: 'flex', 
        flexDirection: 'column',
        background: 'var(--bg-raised)'
      }}>
        <div style={{ padding: '32px 24px' }}>
          <button 
            onClick={() => router.push('/library')} 
            style={{ 
              display: 'inline-flex', 
              alignItems: 'center', 
              gap: '8px', 
              color: 'var(--text-muted)', 
              fontSize: 'var(--text-xs)', 
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              marginBottom: '32px',
              transition: 'color 0.15s ease'
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
          >
            <ArrowLeft size={12} />
            {t('common.backToLibrary')}
          </button>
          
          <div style={{ marginBottom: '40px' }}>
            <h2 className="serif" style={{ fontSize: 'var(--text-xl)', marginBottom: '8px' }}>
              {book ? `《${book.title}》` : t('chat.bookLoading')}
            </h2>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
              <div style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--status-ok)' }}></div>
              {t('chat.semanticLoaded')}
            </div>
          </div>

          <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <ModeButton 
              active={mode === 'rag'} 
              onClick={() => { setMode('rag'); setMessages([]) }}
              icon={<BookOpen size={16} />}
              title={t('chat.mode.rag.title')}
              desc={t('chat.mode.rag.desc')}
            />
            <ModeButton 
              active={mode === 'agent'} 
              onClick={() => { setMode('agent'); setMessages([]) }}
              icon={<Cpu size={16} />}
              title={t('chat.mode.agent.title')}
              desc={t('chat.mode.agent.desc')}
              accent={true}
            />
          </nav>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
        
        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '64px 40px' }}>
          {messages.length === 0 ? (
            <div style={{ 
              height: '100%', 
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              flexDirection: 'column',
              opacity: 0.4
            }}>
              {mode === 'rag' ? <BookOpen size={48} strokeWidth={0.8} /> : <Sparkles size={48} strokeWidth={0.8} />}
              <h3 className="serif" style={{ fontSize: 'var(--text-lg)', marginTop: '24px' }}>
                {mode === 'rag' ? t('chat.empty.rag.title') : t('chat.empty.agent.title')}
              </h3>
              <p style={{ maxWidth: '360px', textAlign: 'center', marginTop: '12px', fontSize: 'var(--text-sm)', lineHeight: 1.6 }}>
                {mode === 'rag' 
                  ? t('chat.empty.rag.desc')
                  : t('chat.empty.agent.desc')}
              </p>
            </div>
          ) : (
            <div style={{ maxWidth: '720px', margin: '0 auto' }}>
              {messages.map((m, i) => (
                <MessageItem key={i} message={m} mode={mode} isLast={i === messages.length - 1} loading={loading} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Input area */}
        <div style={{ 
          padding: '40px', 
          background: 'linear-gradient(to top, var(--bg) 80%, transparent)', 
          display: 'flex', 
          justifyContent: 'center' 
        }}>
          <div style={{ maxWidth: '720px', width: '100%', position: 'relative' }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSend()
                }
              }}
              placeholder={mode === 'rag' ? t('chat.input.rag') : t('chat.input.agent')}
              rows={1}
              disabled={loading}
              style={{
                width: '100%', 
                padding: '18px 24px', 
                paddingRight: '64px',
                background: 'var(--bg-raised)', 
                border: '1px solid var(--border)',
                borderRadius: '16px', 
                color: 'var(--text-primary)', 
                fontSize: 'var(--text-base)',
                resize: 'none', 
                overflow: 'hidden', 
                minHeight: '60px',
                outline: 'none',
                boxShadow: '0 8px 32px -8px rgba(0,0,0,0.4)',
                transition: 'border-color 0.2s ease'
              }}
              onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hover)'}
              onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
              onInput={(e) => {
                const target = e.target as HTMLTextAreaElement
                target.style.height = 'auto'
                target.style.height = Math.min(target.scrollHeight, 240) + 'px'
              }}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              style={{
                position: 'absolute', 
                right: '12px', 
                top: '50%', 
                transform: 'translateY(-50%)',
                background: input.trim() ? 'var(--text-primary)' : 'var(--border)',
                color: 'var(--bg)',
                border: 'none',
                width: '36px',
                height: '36px',
                borderRadius: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: input.trim() ? 'pointer' : 'default',
                transition: 'all 0.15s ease'
              }}
            >
              {loading ? <Loader2 size={16} style={{ animation: 'spin 1.4s linear infinite' }} /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </main>

      {/* Right Sidebar (Sources for RAG) */}
      {mode === 'rag' && messages.some(m => m.sources && m.sources.length > 0) && (
        <aside style={{ 
          width: '380px', 
          borderLeft: '1px solid var(--border)', 
          display: 'flex', 
          flexDirection: 'column',
          background: 'var(--bg-raised)'
        }}>
          <div style={{ padding: '24px', borderBottom: '1px solid var(--border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-secondary)' }}>
              <Quote size={14} />
              <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{t('chat.source.title')}</h3>
            </div>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
             {messages.filter(m => m.sources).slice(-1).map((msg, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  {msg.sources?.map((s: any, idx) => (
                    <div key={idx} style={{ 
                      padding: '20px', 
                      background: 'var(--bg)', 
                      border: '1px solid var(--border)', 
                      borderRadius: '12px' 
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
                        <span style={{ fontSize: '11px', color: 'var(--accent)', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <Hash size={10} /> {s.chapter || t('common.chapterDefault')}
                        </span>
                        {s.page && <span style={{ fontSize: '11px', opacity: 0.4 }}>P.{s.page}</span>}
                      </div>
                      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', lineHeight: 1.6, fontStyle: 'italic' }}>
                        &quot;{s.quote}&quot;
                      </p>
                    </div>
                  ))}
                </div>
              ))}
          </div>
        </aside>
      )}

    </div>
  )
}

function ModeButton({ active, onClick, icon, title, desc, accent = false }: any) {
  return (
    <button 
      onClick={onClick}
      style={{
        textAlign: 'left', 
        padding: '20px', 
        borderRadius: '14px',
        backgroundColor: active ? (accent ? 'rgba(var(--accent-rgb), 0.1)' : 'var(--bg)') : 'transparent',
        border: '1px solid',
        borderColor: active ? (accent ? 'var(--accent)' : 'var(--border-hover)') : 'transparent',
        cursor: 'pointer', 
        transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
        display: 'block',
        width: '100%'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px', color: active ? 'var(--text-primary)' : 'var(--text-muted)' }}>
        {icon}
        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{title}</span>
      </div>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5, opacity: active ? 1 : 0.6 }}>
        {desc}
      </div>
    </button>
  )
}

function MessageItem({ message, mode, isLast, loading }: { message: Message, mode: Mode, isLast: boolean, loading: boolean }) {
  const { t } = useI18n()
  const isUser = message.role === 'user'
  
  return (
    <div style={{ 
      marginBottom: '48px', 
      display: 'flex', 
      gap: '24px', 
      flexDirection: isUser ? 'row-reverse' : 'row' 
    }}>
      {/* Avatar / Role */}
      <div style={{ 
        width: '32px', 
        height: '32px', 
        borderRadius: '8px', 
        background: isUser ? 'var(--border)' : (mode === 'rag' ? 'var(--bg-raised)' : 'rgba(var(--accent-rgb), 0.1)'),
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        color: isUser ? 'var(--text-secondary)' : (mode === 'rag' ? 'var(--text-muted)' : 'var(--accent)'),
        border: '1px solid var(--border)',
        marginTop: '4px'
      }}>
        {isUser ? <MessageSquare size={14} /> : (mode === 'rag' ? <BookOpen size={14} /> : <Sparkles size={14} />)}
      </div>

      {/* Bubble */}
      <div style={{ 
        maxWidth: '85%', 
        display: 'flex', 
        flexDirection: 'column', 
        alignItems: isUser ? 'flex-end' : 'flex-start' 
      }}>
        <div style={{
          fontSize: 'var(--text-base)',
          color: isUser ? 'var(--text-primary)' : 'inherit',
          lineHeight: 1.7
        }}>
          {isUser ? (
             <div style={{ 
               background: 'var(--bg-raised)', 
               padding: '12px 20px', 
               borderRadius: '16px 4px 16px 16px',
               border: '1px solid var(--border)'
             }}>
               {message.content}
             </div>
          ) : message.content === '__LOADING__' ? (
            <ThinkingIndicator mode={mode} />
          ) : (
            <div className="custom-markdown" style={{ opacity: (loading && isLast) ? 0.6 : 1 }}>
              <ReactMarkdown 
                remarkPlugins={[remarkGfm]} 
                rehypePlugins={[rehypeRaw, rehypeSanitize]}
              >
                {message.content || '...'}
              </ReactMarkdown>
            </div>
          )}
        </div>
        
        {!isUser && message.sources && (
          <div style={{ 
            marginTop: '16px', 
            padding: '6px 12px', 
            borderRadius: '6px', 
            background: 'var(--bg-raised)', 
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '11px',
            color: 'var(--text-muted)',
            cursor: 'default'
          }}>
            <Quote size={10} />
            {t('chat.source.count', { count: message.sources.length })}
          </div>
        )}
      </div>
    </div>
  )
}

function ThinkingIndicator({ mode }: { mode: Mode }) {
  const { t } = useI18n()
  const [dots, setDots] = useState(0)
  const texts = mode === 'rag' 
    ? [t('chat.thinking.rag.1'), t('chat.thinking.rag.2'), t('chat.thinking.rag.3'), t('chat.thinking.rag.4')]
    : [t('chat.thinking.agent.1'), t('chat.thinking.agent.2'), t('chat.thinking.agent.3'), t('chat.thinking.agent.4')]
  
  useEffect(() => {
    const interval = setInterval(() => {
      setDots(prev => (prev + 1) % 4)
    }, 600)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ 
      background: 'var(--bg-raised)', 
      padding: '16px 24px', 
      borderRadius: '4px 16px 16px 16px',
      border: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      gap: '12px'
    }}>
      <div style={{ 
        width: '20px', 
        height: '20px', 
        position: 'relative',
      }}>
        <Loader2 
          size={20} 
          style={{ 
            animation: 'spin 1s linear infinite',
            color: 'var(--accent)'
          }} 
        />
      </div>
      <span style={{ 
        color: 'var(--text-secondary)', 
        fontSize: 'var(--text-sm)',
        minWidth: '120px'
      }}>
        {texts[dots]}{'.'.repeat(dots + 1)}
      </span>
    </div>
  )
}
