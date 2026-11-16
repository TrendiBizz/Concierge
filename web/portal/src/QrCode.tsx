import {useMemo} from 'react';
import qrcode from 'qrcode-generator';

/**
 * A QR code for a link we own, drawn in the browser.
 *
 * Nothing about the customer leaves the page and there is no external QR service to depend on.
 * `qrSvg` is the same drawing as a standalone SVG, for a download that can be printed on a card,
 * a van or a quote.
 */
export function qrSvg(value: string, cellSize = 8): string {
  try {
    const code = qrcode(0, 'M');
    code.addData(value);
    code.make();
    return code.createSvgTag({cellSize, margin: 4, scalable: false});
  } catch {
    return '';
  }
}

export function QrCode({value, size = 160, label = 'QR code'}: {value: string; size?: number; label?: string}) {
  const svg = useMemo(() => {
    try {
      const code = qrcode(0, 'M');
      code.addData(value);
      code.make();
      return code.createSvgTag({cellSize: 4, margin: 4, scalable: true});
    } catch {
      return '';
    }
  }, [value]);
  if (!svg) return null;
  const scaled = svg.replace('<svg ', '<svg aria-hidden="true" focusable="false" style="width:100%;height:100%;display:block" ');
  return (
    <div style={{width: size, height: size, background: '#fff', padding: 6, borderRadius: 8, border: '1px solid var(--color-border)'}}
         role="img" aria-label={label}
         dangerouslySetInnerHTML={{__html: scaled}} />
  );
}

export function qrDownloadHref(value: string): string {
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(qrSvg(value));
}
