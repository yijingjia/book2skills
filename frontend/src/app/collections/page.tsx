'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, Layers, Loader2, Plus } from 'lucide-react'
import { CollectionSummary, listCollections } from '@/lib/api'
import { useI18n } from '@/lib/i18n'

export default function CollectionsPage() {
  const { t, locale } = useI18n()
  const [collections, setCollections] = useState<CollectionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCollections()
      .then(setCollections)
      .catch(() => setError(t('collections.loadFailed')))
      .finally(() => setLoading(false))
  }, [t])

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

      <header style={{
        marginBottom: '32px',
        display: 'flex',
        justifyContent: 'space-between',
        gap: '16px',
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        <div>
          <h1 className="serif" style={{ fontSize: 'var(--text-2xl)', marginBottom: '8px' }}>
            {t('collections.allTitle')}
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
            {t('collections.bookCount', { count: collections.length })}
          </p>
        </div>
        <Link href="/collections/new" className="btn-primary" style={{ textDecoration: 'none' }}>
          <Plus size={14} strokeWidth={2} />
          {t('collections.new')}
        </Link>
      </header>

      {loading && (
        <div style={{ color: 'var(--text-muted)', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Loader2 size={16} style={{ animation: 'spin 1.4s linear infinite' }} />
          {t('common.loading')}
        </div>
      )}

      {error && <div className="alert-error">{error}</div>}

      {!loading && !error && collections.length === 0 && (
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)', padding: '32px 0' }}>
          {t('collections.empty')}
        </div>
      )}

      {!loading && !error && collections.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {collections.map((collection, i) => (
            <Link
              key={collection.id}
              href={`/collections/${collection.id}`}
              style={{
                padding: '18px 0',
                borderBottom: i === collections.length - 1 ? 'none' : '1px solid var(--border)',
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
                  marginBottom: '4px',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
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
          ))}
        </div>
      )}
    </main>
  )
}
