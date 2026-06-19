'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Plus, Loader2, BookOpen, AlertCircle, Inbox, Layers } from 'lucide-react'
import { CollectionSummary, listBooks, generateSkill, listCollections } from '@/lib/api'
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

export default function LibraryPage() {
  const { t, locale } = useI18n()
  const router = useRouter()
  const [books, setBooks] = useState<Book[]>([])
  const [collections, setCollections] = useState<CollectionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [generatingFor, setGeneratingFor] = useState<string | null>(null)
  const recentCollections = collections.slice(0, 5)

  const handleRegenerate = async (bookId: string) => {
    setGeneratingFor(bookId)
    try {
      const res = await generateSkill(bookId)
      router.push(`/books/${bookId}/skills/${res.id}`)
    } catch (e: any) {
      alert(e.message || t('library.error.regenerateFailed'))
      setGeneratingFor(null)
    }
  }

  useEffect(() => {
    Promise.allSettled([listBooks(), listCollections()])
      .then(([booksResult, collectionsResult]) => {
        if (booksResult.status === 'rejected') {
          setError('library.loadFailed')
          return
        }
        setBooks(booksResult.value)
        if (collectionsResult.status === 'fulfilled') {
          setCollections(collectionsResult.value)
        }
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <main style={{ maxWidth: '720px', margin: '0 auto', padding: '0 24px 80px', minHeight: '100vh' }}>

      {/* Nav */}
      <nav style={{
        padding: '20px 0',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border)',
        marginBottom: '48px',
      }}>
        <Link
          href="/"
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: 'var(--text-lg)',
            color: 'var(--text-primary)',
            textDecoration: 'none',
          }}
        >
          book2skills
        </Link>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Link href="/collections/new" className="btn-secondary" style={{ textDecoration: 'none' }}>
            <Layers size={14} strokeWidth={2} />
            {t('collections.new')}
          </Link>
          <Link href="/" className="btn-primary" style={{ textDecoration: 'none' }}>
            <Plus size={14} strokeWidth={2} />
            {t('library.uploadNewBook')}
          </Link>
        </div>
      </nav>

      {/* Header */}
      <header style={{ marginBottom: '40px' }}>
        <h1 style={{
          fontFamily: 'var(--font-serif)',
          fontSize: 'clamp(1.6rem, 3vw, 2rem)',
          fontWeight: 400,
          letterSpacing: '-0.02em',
          marginBottom: '8px',
        }}>
          {t('library.title')}
        </h1>
        {!loading && !error && (
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
            {t('library.summary', {
              total: books.length,
              ready: books.filter(b => b.status === 'ready').length,
            })}
          </p>
        )}
      </header>

      {/* Loading */}
      {loading && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '40px 0',
          color: 'var(--text-muted)',
          fontSize: '14px',
        }}>
          <Loader2 size={16} strokeWidth={1.5} style={{ animation: 'spin 1.4s linear infinite' }} />
          {t('library.loading')}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="alert-error" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <AlertCircle size={15} strokeWidth={1.5} />
          {error === 'library.loadFailed' ? t('library.loadFailed') : error}
        </div>
      )}

      {/* Empty */}
      {!loading && !error && books.length === 0 && (
        <div style={{
          padding: '80px 0',
          textAlign: 'center',
          color: 'var(--text-muted)',
        }}>
          <Inbox size={36} strokeWidth={0.8} style={{ marginBottom: '16px', opacity: 0.5 }} />
          <p style={{ fontSize: '14px', marginBottom: '20px' }}>{t('library.empty')}</p>
          <Link href="/" className="btn-secondary" style={{ textDecoration: 'none' }}>
            {t('library.uploadFirst')}
          </Link>
        </div>
      )}

      {/* Collection list */}
      {!loading && !error && (books.length > 0 || collections.length > 0) && (
        <section style={{ marginBottom: '40px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 500 }}>
              {t('collections.librarySection')}
            </h2>
            <Link href="/collections" style={{ color: 'var(--text-muted)', fontSize: 'var(--text-xs)', textDecoration: 'none' }}>
              {t('collections.viewAll')}
            </Link>
          </div>

          {collections.length > 0 ? (
            <div style={{ borderTop: '1px solid var(--border)' }}>
              {recentCollections.map((collection, i) => (
                <CollectionRow
                  key={collection.id}
                  collection={collection}
                  isLast={i === recentCollections.length - 1}
                  locale={locale}
                />
              ))}
            </div>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: '12px 0' }}>
              {t('collections.empty')}
            </div>
          )}
        </section>
      )}

      {/* Book list */}
      {!loading && !error && books.length > 0 && (
        <div>
          {books.map((book, i) => (
            <BookRow
              key={book.book_id}
              book={book}
              isLast={i === books.length - 1}
              onRegenerate={handleRegenerate}
              generating={generatingFor === book.book_id}
              locale={locale}
            />
          ))}
        </div>
      )}
    </main>
  )
}

function CollectionRow({
  collection, isLast, locale,
}: {
  collection: CollectionSummary
  isLast: boolean
  locale: 'zh' | 'en'
}) {
  const { t } = useI18n()

  return (
    <Link
      href={`/collections/${collection.id}`}
      style={{
        padding: '16px 0',
        borderBottom: isLast ? 'none' : '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        gap: '14px',
        color: 'var(--text-primary)',
        textDecoration: 'none',
      }}
    >
      <div style={{
        width: '34px',
        height: '34px',
        borderRadius: '6px',
        background: 'var(--bg-raised)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        <Layers size={15} strokeWidth={1.5} style={{ color: 'var(--text-muted)' }} />
      </div>

      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{
          fontWeight: 500,
          fontSize: 'var(--text-sm)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          marginBottom: '4px',
        }}>
          {collection.name}
        </div>
        <div style={{
          fontSize: 'var(--text-xs)',
          color: 'var(--text-muted)',
          display: 'flex',
          gap: 'var(--space-3)',
          flexWrap: 'wrap',
        }}>
          {collection.description && <span>{collection.description}</span>}
          <span>{t('collections.bookCount', { count: collection.book_count })}</span>
          <span>{new Date(collection.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US')}</span>
        </div>
      </div>
    </Link>
  )
}

function BookRow({
  book, isLast, onRegenerate, generating, locale,
}: {
  book: Book
  isLast: boolean
  onRegenerate: (id: string) => void
  generating: boolean
  locale: 'zh' | 'en'
}) {
  const { t } = useI18n()
  const canView = book.skill_id && book.skill_status === 'ready'
  const isFailed = book.skill_status === 'error'
  const isGenerating = book.skill_status === 'generating'

  const statusColor =
    book.status === 'ready'      ? 'var(--status-ok)' :
    book.status === 'processing' ? 'var(--status-info)' :
    book.status === 'error'      ? 'var(--status-error)' :
                                   'var(--text-muted)'

  const skillStatusColor =
    book.skill_status === 'ready'      ? 'var(--status-ok)' :
    book.skill_status === 'generating' ? 'var(--status-warn)' :
    book.skill_status === 'error'      ? 'var(--status-error)' :
                                         'var(--text-muted)'

  const statusKey = `library.status.${book.status}`
  const statusLabel = t(statusKey)
  const safeStatusLabel = statusLabel === statusKey ? book.status : statusLabel

  const skillStatusKey = book.skill_status ? `library.skill.${book.skill_status}` : ''
  const skillStatusLabel = skillStatusKey ? t(skillStatusKey) : ''
  const safeSkillStatusLabel = skillStatusKey && skillStatusLabel === skillStatusKey
    ? book.skill_status
    : skillStatusLabel

  return (
    <div style={{
      padding: '20px 0',
      borderBottom: isLast ? 'none' : '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      transition: 'background 0.15s ease',
    }}>
      {/* Book icon */}
      <div style={{
        width: '36px',
        height: '36px',
        borderRadius: '6px',
        background: 'var(--bg-raised)',
        border: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        <BookOpen size={15} strokeWidth={1.5} style={{ color: 'var(--text-muted)' }} />
      </div>

      {/* Meta */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 500,
          fontSize: 'var(--text-base)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          marginBottom: 'var(--space-1)',
        }}>
          {book.title || t('common.unknownBookTitle')}
        </div>

        <div style={{
          display: 'flex',
          gap: 'var(--space-3)',
          fontSize: 'var(--text-xs)',
          color: 'var(--text-muted)',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}>
          {book.author && <span>{book.author}</span>}
          {book.page_count && <span>{book.page_count} {t('common.pageUnit')}</span>}
          <span>{new Date(book.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US')}</span>

          <span style={{ color: statusColor }}>
            {safeStatusLabel}
          </span>

          {book.skill_status && (
            <span style={{ color: skillStatusColor }}>
              {safeSkillStatusLabel}
            </span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', flexShrink: 0, alignItems: 'center' }}>

        {book.status === 'ready' && (
          <Link
            href={`/books/${book.book_id}/chat`}
            style={{
              fontSize: '12px',
              color: 'var(--text-primary)',
              textDecoration: 'none',
              padding: '6px 12px',
              border: '1px solid var(--border-hover)',
              borderRadius: '6px',
              transition: 'color 0.15s ease, border-color 0.15s ease, opacity 0.15s ease',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.opacity = '0.7'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.opacity = '1'
            }}
          >
            {t('library.chatWithBook')}
          </Link>
        )}

        {canView && book.skill_id && (
          <Link
            href={`/books/${book.book_id}/skills/${book.skill_id}`}
            className="btn-primary"
            style={{ textDecoration: 'none', fontSize: '12px', padding: '6px 14px' }}
          >
            {t('library.viewSkill')}
          </Link>
        )}

        {book.status === 'ready' && !book.skill_id && (
          <button
            onClick={() => onRegenerate(book.book_id)}
            disabled={generating}
            className="btn-secondary"
            style={{ fontSize: '12px', padding: '6px 14px' }}
          >
            {generating ? (
              <><Loader2 size={12} style={{ animation: 'spin 1.4s linear infinite' }} /> {t('library.skill.generating')}</>
            ) : t('library.generateSkill')}
          </button>
        )}

        {book.skill_id && isGenerating && (
          <Link
            href={`/books/${book.book_id}/skills/${book.skill_id}`}
            className="btn-ghost"
            style={{ textDecoration: 'none', fontSize: '12px' }}
          >
            {t('library.viewSkill')}
          </Link>
        )}

        {(isFailed || isGenerating) && (
          <button
            onClick={() => onRegenerate(book.book_id)}
            disabled={generating}
            className="btn-ghost"
            style={{ fontSize: '12px' }}
          >
            {generating ? (
              <><Loader2 size={12} style={{ animation: 'spin 1.4s linear infinite' }} /> {t('library.retrying')}</>
            ) : t('library.retry')}
          </button>
        )}
      </div>
    </div>
  )
}
