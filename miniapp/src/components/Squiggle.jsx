/** Оранжевая волнистая черта под заголовком — фирменный штрих референса. */
export default function Squiggle({ width = 44 }) {
  return (
    <svg className="squiggle" width={width} height="8" viewBox="0 0 44 8" fill="none" aria-hidden="true">
      <path d="M2 5.2C9 1 14 1 20 4s16 3.4 22-2" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}
