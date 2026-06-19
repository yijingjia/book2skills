'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, BookOpen, Layers, Loader2 } from 'lucide-react'
import { CollectionDetail, getCollection } from '@/lib/api'
import { useI18n } from '@/lib/i18n'

export default function CollectionDetailPage() {
  const { t } = useI18n()
  const params = useParams()
  const collectionId = params.collectionId as string
  const [collection, setCollection] = useState<CollectionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!collectionId) return
    getCollection(collectionId)
      .then(setCollection)
      .catch(() => setError(t('collections.loadFailed')))
      .finally(() => setLoading(false))
  }, [collectionId, t])

  if (loading) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
        <Loader2 size={28} style={{ animation: 'spin 1.4s linear infinite' }} />
      </main>
    )
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

      {error && <div className="alert-error">{error}</div>}

      {collection && (
        <>
          <header style={{
            marginBottom: '40px',
            display: 'flex',
            justifyContent: 'space-between',
            gap: '24px',
            alignItems: 'flex-start',
            flexWrap: 'wrap',
          }}>
            <div style={{ minWidth: 0, flex: '1 1 360px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: 'var(--text-muted)',
                fontSize: 'var(--text-xs)',
                marginBottom: '8px',
              }}>
                <Layers size={14} />
                {t('collections.title')}
              </div>
              <h1 className="serif" style={{ fontSize: 'var(--text-2xl)', marginBottom: '8px' }}>
                {collection.name}
              </h1>
              {collection.description && (
                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                  {collection.description}
                </p>
              )}
            </div>
            <button
              className="btn-secondary"
              disabled
              title={t('collections.generateComingSoon')}
              style={{ whiteSpace: 'normal', maxWidth: '220px', textAlign: 'center' }}
            >
              {t('collections.generateComingSoon')}
            </button>
          </header>

          <section>
            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 500, marginBottom: '12px' }}>
              {t('collections.sourceBooks')}
            </h2>
            <div style={{ borderTop: '1px solid var(--border)' }}>
              {collection.books.map(book => (
                <div
                  key={book.book_id}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    padding: '16px 0',
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'center',
                  }}
                >
                  <div style={{
                    width: '30px',
                    height: '30px',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <BookOpen size={14} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                      {book.title || t('common.unknownBookTitle')}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {book.author || ''}{book.page_count ? ` · ${book.page_count} ${t('common.pageUnit')}` : ''}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </main>
  )
}
