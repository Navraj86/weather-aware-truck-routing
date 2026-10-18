import { useEffect, useId, useRef, useState } from "react";
import { geocode } from "../api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  placeholder?: string;
}

export function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [results, setResults] = useState<Place[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false);

  // Keep the text in sync when the parent sets a place (pick, swap, sample trips).
  // A null value means the user is typing, so the text is left alone.
  useEffect(() => {
    if (!value) return;
    typed.current = false;
    setText(value.label);
  }, [value]);

  useEffect(() => {
    if (!typed.current || text.trim().length < 2) {
      setResults([]);
      return;
    }
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      geocode(text, ctrl.signal)
        .then((r) => {
          setResults(r);
          setActive(0);
          setOpen(true);
        })
        .catch(() => !ctrl.signal.aborted && setResults([]))
        .finally(() => !ctrl.signal.aborted && setLoading(false));
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [text]);

  const choose = (p: Place) => {
    onChange(p);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const listId = `${id}-list`;
  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <div className="combo">
        <input
          id={id}
          type="text"
          autoComplete="off"
          role="combobox"
          aria-expanded={open && results.length > 0}
          aria-controls={listId}
          aria-activedescendant={open && results.length ? `${listId}-${active}` : undefined}
          placeholder={placeholder}
          value={text}
          onChange={(e) => {
            typed.current = true;
            setText(e.target.value);
            if (value) onChange(null);
          }}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKeyDown}
          className={value ? "is-set" : undefined}
        />
        {loading && <span className="combo-spinner" aria-hidden />}
        {open && results.length > 0 && (
          <ul className="combo-list" id={listId} role="listbox">
            {results.map((r, i) => (
              <li
                key={`${r.lat},${r.lon},${i}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === active}
                className={i === active ? "active" : undefined}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(r);
                }}
                onMouseEnter={() => setActive(i)}
              >
                {r.label}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
