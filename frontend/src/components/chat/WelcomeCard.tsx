const TEXT = 'Trading with TuanTuan'

export function WelcomeCard() {
  return (
    <h1 className="text-[40px] font-semibold tracking-tight text-[var(--color-text-primary)]">
      {TEXT.split('').map((char, i) => (
        <span
          key={i}
          className="hero-char inline-block"
          style={{
            opacity: 0,
            animation: 'hero-char-in 0.35s ease-out forwards',
            animationDelay: `${i * 0.04}s`,
          }}
        >
          {char === ' ' ? '\u00A0' : char}
        </span>
      ))}
    </h1>
  )
}
