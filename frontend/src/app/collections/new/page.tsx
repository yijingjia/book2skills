'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, BookOpen, Check, Loader2 } from 'lucide-react'
import { createCollection, listBooks } from '@/lib/api'
import { useI18n } from '@/lib/i18n'

type Book = {
  book_id: string
  title: string | null
  author: string | null
  status: string
  page_count: number | null
  created_at: string
  skill_id: string | null
  skill_status: string | null
}

const fieldStyle: React.CSSProperties = {
  width: '100%',
  border: '1px solid var(--border)',
  borderRadius: '6px',
  background: 'var(--bg)',
  color: 'var(--text-primary)',
  font: 'inherit',
  fontSize: 'var(--text-sm)',
  padding: '12px 14px',
  outline: 'none',
}

export default function NewCollectionPage() {
  const { t } = useI18n()
  const router = useRouter()
  const [books, setBooks] = useState<Book[]>([])
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selected, setSelected] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listBooks()
      .then(setBooks)
      .catch(() => setError(t('library.loadFailed')))
      .finally(() => setLoading(false))
  }, [t])

  const readyBooks = useMemo(() => books.filter(book => book.status === 'ready'), [books])
  const canSubmit = name.trim().length > 0 && selected.length >= 2 && !saving

  const toggleBook = (bookId: string) => {
    setSelected(current =>
      current.includes(bookId)
        ? current.filter(id => id !== bookId)
        : [...current, bookId]
    )
  }

  const handleSubmit = async () => {
    if (!canSubmit) return
    setSaving(true)
    setError(null)
    try {
      const collection = await createCollection({
        name: name.trim(),
        description: description.trim() || null,
        book_ids: selected,
      })
      router.push(`/collections/${collection.id}`)
    } catch (e: any) {
      setError(e.message || t('collections.createFailed'))
      setSaving(false)
    }
  }

  return (
    <main style={{ maxWidth: '760px', margin: '0 auto', padding: '48px 24px 120px' }}>
      <Link
        href="/library"
        style={{
          display: 'inline-flex',
          gap: '6px',
          alignItems: 'center',
          color: 'var(--text-muted)',
          fontSize: 'var(--text-xs)',
          textDecoration: 'none',
          marginBottom: '24px',
        }}
      >
        <ArrowLeft size={12} />
        {t('common.backToLibrary')}
      </Link>

      <header style={{ marginBottom: '32px' }}>
        <h1 className="serif" style={{ fontSize: 'var(--text-2xl)', marginBottom: '8px' }}>
          {t('collections.new')}
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
          {t('collections.readyBooksOnly')}
        </p>
      </header>

      {error && <div className="alert-error" style={{ marginBottom: '24px' }}>{error}</div>}

      <section style={{ display: 'grid', gap: '16px', marginBottom: '32px' }}>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder={t('collections.name')}
          style={fieldStyle}
        />
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder={t('collections.description')}
          rows={4}
          style={{ ...fieldStyle, resize: 'vertical', minHeight: '112px' }}
        />
      </section>

      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '16px', marginBottom: '12px' }}>
          <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 500 }}>{t('collections.selectBooks')}</h2>
          <span style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)', whiteSpace: 'nowrap' }}>
            {t('collections.selectedCount', { count: selected.length })}
          </span>
        </div>

        {loading ? (
          <div style={{ color: 'var(--text-muted)', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <Loader2 size={16} style={{ animation: 'spin 1.4s linear infinite' }} />
            {t('common.loading')}
          </div>
        ) : (
          <div style={{ borderTop: '1px solid var(--border)' }}>
            {readyBooks.map(book => {
              const checked = selected.includes(book.book_id)
              return (
                <button
                  key={book.book_id}
                  type="button"
                  onClick={() => toggleBook(book.book_id)}
                  style={{
                    width: '100%',
                    border: 'none',
                    borderBottom: '1px solid var(--border)',
                    background: 'transparent',
                    padding: '16px 0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    color: 'var(--text-primary)',
                  }}
                >
                  <div style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: '6px',
                    border: checked ? '1px solid var(--text-primary)' : '1px solid var(--border)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    {checked ? <Check size={14} /> : <BookOpen size={14} />}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{
                      fontSize: 'var(--text-sm)',
                      fontWeight: 500,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}>
                      {book.title || t('common.unknownBookTitle')}
                    </div>
                    {book.author && (
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '4px' }}>
                        {book.author}
                      </div>
                    )}
                  </div>
                </button>
              )
            })}
          </div>
        )}
      </section>

      <div style={{ marginTop: '32px', display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-primary" disabled={!canSubmit} onClick={handleSubmit}>
          {saving && <Loader2 size={14} style={{ animation: 'spin 1.4s linear infinite' }} />}
          {t('collections.create')}
        </button>
      </div>
    </main>
  )
}
