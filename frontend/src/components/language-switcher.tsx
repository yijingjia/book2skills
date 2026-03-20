'use client'

import { useI18n } from '@/lib/i18n'

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useI18n()

  return (
    <div
      aria-label="Language switcher"
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: '2px',
        border: '1px solid var(--border)',
        borderRadius: '999px',
        background: 'var(--bg-raised)',
      }}
    >
      {(['zh', 'en'] as const).map((lang) => {
        const active = locale === lang
        return (
          <button
            key={lang}
            type="button"
            onClick={() => setLocale(lang)}
            aria-label={lang === 'zh' ? 'Switch language to Chinese' : 'Switch language to English'}
            aria-pressed={active}
            style={{
              border: 'none',
              borderRadius: '999px',
              padding: '4px 10px',
              fontSize: '11px',
              letterSpacing: '0.04em',
              background: active ? 'var(--text-primary)' : 'transparent',
              color: active ? 'var(--bg)' : 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            {lang === 'zh' ? t('language.zh') : t('language.en')}
          </button>
        )
      })}
    </div>
  )
}
