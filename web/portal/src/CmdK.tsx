import {useEffect, useMemo, useState} from 'react';
import {Dialog} from '@astryxdesign/core/Dialog';
import {TextInput} from '@astryxdesign/core/TextInput';
import {Button} from '@astryxdesign/core/Button';
import {Text} from '@astryxdesign/core/Text';
import {VStack} from '@astryxdesign/core/VStack';

export type Command = {id: string; label: string; group?: string; run: () => void};

/**
 * ⌘K / Ctrl-K jump-to-anything.
 *
 * The Studio has fifteen nav items in four groups; hunting them with the mouse is the slowest
 * thing on a big screen. This is Astryx's Dialog + our own filtering rather than a bespoke modal,
 * so focus trapping, escape and scrim come from the design system.
 */
export function CmdK({commands}: {commands: Command[]}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setIsOpen((open) => !open);
        setQuery('');
        setActive(0);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return commands.filter((command) =>
      !needle
      || command.label.toLowerCase().includes(needle)
      || (command.group || '').toLowerCase().includes(needle));
  }, [commands, query]);

  function close() { setIsOpen(false); setQuery(''); setActive(0); }

  function runAt(index: number) {
    const command = matches[index];
    if (!command) return;
    close();
    command.run();
  }

  return (
    <Dialog isOpen={isOpen} onOpenChange={(open) => { if (!open) close(); }}>
      <VStack gap={2}>
        <TextInput label="Jump to" value={query} hasAutoFocus
                   onChange={(value) => { setQuery(value); setActive(0); }}
                   onKeyDown={(event: React.KeyboardEvent) => {
                     if (event.key === 'ArrowDown') {
                       event.preventDefault();
                       setActive((current) => Math.min(current + 1, matches.length - 1));
                     } else if (event.key === 'ArrowUp') {
                       event.preventDefault();
                       setActive((current) => Math.max(current - 1, 0));
                     } else if (event.key === 'Enter') {
                       event.preventDefault();
                       runAt(active);
                     }
                   }} />
        {matches.length ? matches.slice(0, 9).map((command, index) => (
          <Button key={command.id} variant={index === active ? 'primary' : 'secondary'}
                  label={(command.group ? command.group + ' · ' : '') + command.label}
                  onClick={() => runAt(index)} />
        )) : <Text>Nothing matches that.</Text>}
        <Text size="sm" color="secondary">↑↓ to move · Enter to go · ⌘K to close</Text>
      </VStack>
    </Dialog>
  );
}
