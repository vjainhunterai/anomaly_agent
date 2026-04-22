import React from 'react';

// Small hand-rolled markdown renderer so we don't need a third-party library.
// Supports: headings (#..####), bold (**x**), italic (*x*), inline `code`,
// fenced ``` code blocks, unordered/ordered lists, and GitHub-style tables.

function escapeHtml(s) {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderInline(text) {
  let t = escapeHtml(text);
  // inline code first so ** inside code isn't mangled
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|\W)\*([^*]+)\*(\W|$)/g, '$1<em>$2</em>$3');
  t = t.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noreferrer noopener">$1</a>'
  );
  return t;
}

function parseTable(lines, start) {
  // a table is: header | header\n---|---\n row | row ...
  const header = lines[start];
  const sep = lines[start + 1] || '';
  if (!/\|/.test(header) || !/^\s*\|?\s*:?-{2,}/.test(sep.trim())) return null;
  const split = (ln) =>
    ln
      .replace(/^\s*\|/, '')
      .replace(/\|\s*$/, '')
      .split('|')
      .map((c) => c.trim());

  const headers = split(header);
  const rows = [];
  let i = start + 2;
  while (i < lines.length && /\|/.test(lines[i]) && lines[i].trim() !== '') {
    rows.push(split(lines[i]));
    i += 1;
  }
  return { headers, rows, nextIndex: i };
}

function renderBlocks(md) {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  let keyCounter = 0;
  const k = () => `md-${keyCounter++}`;

  while (i < lines.length) {
    const line = lines[i];

    // fenced code block
    if (/^```/.test(line.trim())) {
      const lang = line.trim().replace(/^```/, '').trim();
      const codeLines = [];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1; // skip closing ```
      blocks.push(
        <pre key={k()} className={`code-block ${lang ? `lang-${lang}` : ''}`}>
          <code>{codeLines.join('\n')}</code>
        </pre>
      );
      continue;
    }

    // heading
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const Tag = `h${level + 1}`; // h2..h5 so the panel H2s don't collide
      blocks.push(
        <Tag
          key={k()}
          dangerouslySetInnerHTML={{ __html: renderInline(h[2]) }}
        />
      );
      i += 1;
      continue;
    }

    // table
    if (line.includes('|') && i + 1 < lines.length) {
      const tbl = parseTable(lines, i);
      if (tbl) {
        blocks.push(
          <div key={k()} className="md-table-wrap">
            <table className="md-table">
              <thead>
                <tr>
                  {tbl.headers.map((h, idx) => (
                    <th
                      key={idx}
                      dangerouslySetInnerHTML={{ __html: renderInline(h) }}
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {tbl.rows.map((r, idx) => (
                  <tr key={idx}>
                    {r.map((c, ci) => (
                      <td
                        key={ci}
                        dangerouslySetInnerHTML={{ __html: renderInline(c) }}
                      />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
        i = tbl.nextIndex;
        continue;
      }
    }

    // unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ul key={k()}>
          {items.map((it, idx) => (
            <li
              key={idx}
              dangerouslySetInnerHTML={{ __html: renderInline(it) }}
            />
          ))}
        </ul>
      );
      continue;
    }

    // ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ol key={k()}>
          {items.map((it, idx) => (
            <li
              key={idx}
              dangerouslySetInnerHTML={{ __html: renderInline(it) }}
            />
          ))}
        </ol>
      );
      continue;
    }

    // blank line
    if (line.trim() === '') {
      i += 1;
      continue;
    }

    // paragraph (consume consecutive non-blank, non-special lines)
    const paraLines = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^```/.test(lines[i].trim()) &&
      !/^#{1,4}\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i += 1;
    }
    blocks.push(
      <p
        key={k()}
        dangerouslySetInnerHTML={{
          __html: renderInline(paraLines.join(' ')),
        }}
      />
    );
  }

  return blocks;
}

export default function MarkdownRenderer({ text, className }) {
  if (!text) return null;
  return <div className={`md ${className || ''}`}>{renderBlocks(text)}</div>;
}
