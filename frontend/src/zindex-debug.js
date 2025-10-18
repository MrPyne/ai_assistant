// Dev-only utility: logs stacking-context creators for a given element
// Usage: import './zindex-debug' and call window.__logStackingContexts(element)
window.__logStackingContexts = function (el) {
  if (!el) return console.warn('Provide an element')
  const path = []
  let cur = el
  while (cur) {
    const styles = window.getComputedStyle(cur)
    const creates = []
    // common stacking context creators
    if (styles.position && styles.position !== 'static' && parseInt(styles.zIndex || 'auto') !== 0) creates.push(`position:${styles.position};z:${styles.zIndex}`)
    if (styles.opacity && Number(styles.opacity) < 1) creates.push(`opacity:${styles.opacity}`)
    if (styles.transform && styles.transform !== 'none') creates.push(`transform:${styles.transform}`)
    if (styles.filter && styles.filter !== 'none') creates.push(`filter:${styles.filter}`)
    if (styles.mixBlendMode && styles.mixBlendMode !== 'normal') creates.push(`mixBlend:${styles.mixBlendMode}`)
    if (styles.willChange && styles.willChange !== 'auto') creates.push(`willChange:${styles.willChange}`)
    path.push({ node: cur, tag: cur.tagName, id: cur.id, classes: cur.className, creators: creates })
    cur = cur.parentElement
  }
  console.group('Stacking context path for', el)
  path.forEach((p, i) => {
    console.log(`#${i}`, p.tag, p.id ? `#${p.id}` : '', p.classes ? `.${p.classes}` : '', p.creators.length ? `=> ${p.creators.join(',')}` : '')
  })
  console.groupEnd()
}
