/** Cor de texto (preto/branco) com maior contraste sobre um fundo hex.
 *  Usa luminância relativa WCAG; retorna HEX (não classe Tailwind — classe
 *  dinâmica seria purgada no v4, mesma razão do `style` inline das tags). */
export function textOn(bg: string): string {
  const hex = bg.replace("#", "").trim();
  const full =
    hex.length === 3
      ? hex
          .split("")
          .map((c) => c + c)
          .join("")
      : hex;
  if (full.length !== 6) return "#ffffff";

  const channel = (i: number) => parseInt(full.slice(i, i + 2), 16) / 255;
  const lin = (c: number) =>
    c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);

  const L =
    0.2126 * lin(channel(0)) +
    0.7152 * lin(channel(2)) +
    0.0722 * lin(channel(4));

  // 0.179 = ponto onde o contraste contra preto iguala o contra branco (WCAG).
  return L > 0.179 ? "#000000" : "#ffffff";
}
