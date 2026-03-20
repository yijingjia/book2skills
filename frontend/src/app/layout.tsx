import type { Metadata } from 'next'
import { cookies } from 'next/headers'
import { DM_Sans, DM_Serif_Display } from 'next/font/google'
import './globals.css'
import { LanguageProvider, type Locale, LOCALE_COOKIE_KEY } from '@/lib/i18n'

const dmSans = DM_Sans({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--loaded-font-sans',
  display: 'swap',
})

const dmSerif = DM_Serif_Display({
  subsets: ['latin'],
  weight: ['400'],
  style: ['normal', 'italic'],
  variable: '--loaded-font-serif',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'book2skills - Turn Books Into AI Skills',
  description: 'Upload EPUB books and generate installable AI skill packages.',
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const cookieStore = await cookies()
  const localeFromCookie = cookieStore.get(LOCALE_COOKIE_KEY)?.value
  const initialLocale: Locale = localeFromCookie === 'en' ? 'en' : 'zh'

  return (
    <html
      lang={initialLocale === 'zh' ? 'zh-CN' : 'en'}
      className={`${dmSans.variable} ${dmSerif.variable}`}
    >
      <body style={{ fontFamily: 'var(--font-sans)' }}>
        <LanguageProvider initialLocale={initialLocale}>{children}</LanguageProvider>
      </body>
    </html>
  )
}
