import {useEffect, useMemo, useState} from 'react';
import {Command as Cmdk} from 'cmdk';

export type Command = {id: string; label: string; group?: string; run: () => void};

/**
 * ⌘K / Ctrl-K jump-to-anything, powered by cmdk.
 *
 * Groups all Studio nav items, ranks matches with cmdk's fuzzy command-score,
 * handles arrow keys + Enter + Escape + focus trapping out of the box, and is
 * styled to Trendi's brand tokens in shell.css.
 */
export function CmdK({commands}: {commands: Command[]}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const groups = useMemo(() => {
    const map = new Map<string, Command[]>();
    for (const cmd of commands) {
      const key = cmd.group || 'Navigation';
      const list = map.get(key) || [];
      list.push(cmd);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [commands]);

  return (
    <Cmdk.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Jump to screen"
      overlayClassName="c-cmdk-overlay"
      contentClassName="c-cmdk-content"
      className="c-cmdk"
    >
      <Cmdk.Input
        className="c-cmdk-input"
        placeholder="Jump to any screen…"
        autoFocus
      />
      <Cmdk.List className="c-cmdk-list">
        <Cmdk.Empty className="c-cmdk-empty">Nothing matches that.</Cmdk.Empty>
        {groups.map(([group, items]) => (
          <Cmdk.Group key={group} heading={group} className="c-cmdk-group">
            {items.map((command) => (
              <Cmdk.Item
                key={command.id}
                value={`${command.group || ''} ${command.label}`}
                className="c-cmdk-item"
                onSelect={() => {
                  setOpen(false);
                  command.run();
                }}
              >
                <span>{command.label}</span>
              </Cmdk.Item>
            ))}
          </Cmdk.Group>
        ))}
      </Cmdk.List>
      <div className="c-cmdk-hint">↑↓ to move · Enter to go · Esc or ⌘K to close</div>
    </Cmdk.Dialog>
  );
}
