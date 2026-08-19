/**
 * メッセージ辞書の `{key}` プレースホルダーを値で置き換える。
 *
 * `String.prototype.replace(pattern, value)` に文字列を直接渡すと、`value` 側に
 * `$&` `$$` `$1` 等の特殊置換パターンが含まれる場合に意図せず展開されてしまう
 * （例: `error.message` に `$&` が含まれると文言が壊れる）。置換関数形式を使うと
 * 戻り値がそのまま挿入され、特殊パターンとして再解釈されないため安全。
 */
export function formatMessage(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (matched: string, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? values[key] : matched,
  )
}
