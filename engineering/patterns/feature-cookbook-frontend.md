# feature-cookbook-frontend

**Issue:** Common frontend recipes — forms, modals, infinite scroll
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need a form. You write it from scratch. The validation
is in 5 places. The submit handler does 10 things. The
error display is broken. You wish you'd used a library.

## Root cause
**Common UI patterns have well-known solutions.** Use them
instead of reinventing.

**Source:** Various frontend guides.

## The "form" pattern with React Hook Form

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  email: z.string().email(),
  password: <redacted-secret>
  displayName: z.string().min(1).max(100),
});

type FormData = z.infer<typeof schema>;

function SignupForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    const res = await fetch('/api/users', { method: 'POST', body: JSON.stringify(data) });
    if (!res.ok) {
      // Handle error
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('email')} aria-invalid={!!errors.email} aria-describedby="email-error" />
      {errors.email && <span id="email-error" role="alert">{errors.email.message}</span>}

      <input type="password" {...register('password')} />
      {errors.password && <span>{errors.password.message}</span>}

      <input {...register('displayName')} />
      {errors.displayName && <span>{errors.displayName.message}</span>}

      <button type="submit">Sign up</button>
    </form>
  );
}
```

The form has validation + a11y + error display.

## The "modal" pattern

```tsx
import { useState, useRef, useEffect } from 'react';

function Modal({ isOpen, onClose, title, children }: ModalProps) {
  const modalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Save the previously focused element
    const previouslyFocused = document.activeElement as HTMLElement;

    // Focus the first focusable
    const firstFocusable = modalRef.current?.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    firstFocusable?.focus();

    // Trap focus
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key !== 'Tab') return;

      const focusables = Array.from(modalRef.current?.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"]):not([disabled])') ?? []);
      const first = focusables[0];
      const last = focusables[focusables.length - 1];

      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="modal-title" ref={modalRef}>
      <h2 id="modal-title">{title}</h2>
      {children}
      <button onClick={onClose}>Close</button>
    </div>
  );
}
```

The modal has focus trap + Escape key + restoration.

## The "infinite scroll" pattern

```tsx
import { useInfiniteQuery } from '@tanstack/react-query';

function InfiniteList() {
  const {
    data,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['posts'],
    queryFn: ({ pageParam }) => fetch(`/api/posts?cursor=${pageParam}`).then(r => r.json()),
    initialPageParam: '',
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });

  return (
    <div>
      {data?.pages.map((page) => (
        page.data.map((post: Post) => <PostCard key={post.id} post={post} />)
      ))}

      <div ref={(el) => {
        if (!el) return;
        const observer = new IntersectionObserver(([entry]) => {
          if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
            fetchNextPage();
          }
        });
        observer.observe(el);
        return () => observer.disconnect();
      }}>
        {isFetchingNextPage ? 'Loading...' : hasNextPage ? 'Load more' : 'End'}
      </div>
    </div>
  );
}
```

The list loads more as the user scrolls.

## The "debounced search" pattern

```tsx
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';

function SearchInput() {
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);

  const { data, isLoading } = useQuery({
    queryKey: ['search', deferredQuery],
    queryFn: () => fetch(`/api/search?q=${deferredQuery}`).then(r => r.json()),
    enabled: deferredQuery.length >= 2,
    staleTime: 60_000,
  });

  return (
    <div>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      {isLoading && <Spinner />}
      {data?.results.map((r: SearchResult) => <SearchResultCard key={r.id} result={r} />)}
    </div>
  );
}
```

The search is debounced; results update smoothly.

## The "toast" pattern

```tsx
import { useState, createContext, useContext } from 'react';

const ToastContext = createContext<{ showToast: (msg: string, type?: 'success' | 'error') => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Array<{ id: string; msg: string; type: string }>>([]);

  const showToast = (msg: string, type: 'success' | 'error' = 'success') => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, msg, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id} role={t.type === 'error' ? 'alert' : 'status'}>
            {t.msg}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
};
```

The toast has a11y + auto-dismiss.

## The "skeleton" pattern

```tsx
function PostCardSkeleton() {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading post">
      <div className="skeleton-line w-60" />
      <div className="skeleton-line w-100" />
      <div className="skeleton-line w-80" />
    </div>
  );
}

function PostList({ isLoading, posts }: { isLoading: boolean; posts: Post[] }) {
  return (
    <div>
      {isLoading ? <PostCardSkeleton /> : posts.map((p) => <PostCard key={p.id} post={p} />)}
    </div>
  );
}
```

The skeleton shows while loading; the user knows content is
coming.

## The "optimistic update" pattern

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';

function useUpdatePost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; title: string }) =>
      fetch(`/api/posts/${input.id}`, { method: 'PATCH', body: JSON.stringify(input) }).then(r => r.json()),

    onMutate: async (input) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ['posts'] });
      const previous = queryClient.getQueryData(['posts']);
      queryClient.setQueryData(['posts'], (old: any) => ({
        ...old,
        pages: old.pages.map((page: any) => ({
          ...page,
          data: page.data.map((p: Post) => p.id === input.id ? { ...p, ...input } : p),
        })),
      }));
      return { previous };
    },

    onError: (err, input, context) => {
      // Roll back
      queryClient.setQueryData(['posts'], context?.previous);
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] });
    },
  });
}
```

The update is optimistic; the UI updates immediately; the
server is updated in the background.

## The "image upload" pattern

```tsx
function ImageUpload({ onUpload }: { onUpload: (url: string) => void }) {
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);

  const handleFile = async (file: File) => {
    setIsUploading(true);

    // 1. Get presigned URL
    const { url, key } = await fetch('/api/uploads/presign', {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, contentType: file.type }),
    }).then(r => r.json());

    // 2. Upload with progress
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => setProgress((e.loaded / e.total) * 100);
      xhr.onload = () => resolve();
      xhr.onerror = () => reject(new Error('Upload failed'));
      xhr.open('PUT', url);
      xhr.setRequestHeader('Content-Type', file.type);
      xhr.send(file);
    });

    // 3. Notify the server
    const result = await fetch('/api/uploads', {
      method: 'POST',
      body: JSON.stringify({ key, contentType: file.type }),
    }).then(r => r.json());

    onUpload(result.url);
    setIsUploading(false);
  };

  return (
    <div>
      <input type="file" accept="image/*" onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])} />
      {isUploading && <progress value={progress} max="100" />}
    </div>
  );
}
```

The upload has progress; the file goes directly to R2.

## The "responsive design" pattern

```css
/* Mobile-first */
.container { padding: 1rem; }

/* Tablet */
@media (min-width: 768px) {
  .container { padding: 2rem; }
}

/* Desktop */
@media (min-width: 1024px) {
  .container { padding: 3rem; max-width: 1200px; margin: 0 auto; }
}
```

The CSS adapts to the screen size.

## The "dark mode" pattern

```tsx
function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    const stored = localStorage.getItem('theme') as 'light' | 'dark' | null;
    if (stored) setTheme(stored);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    localStorage.setItem('theme', theme);
  }, [theme]);

  return { theme, setTheme };
}
```

The theme is stored in localStorage + applied to the HTML
element.

```css
:root {
  --bg: white;
  --text: black;
}

:root.dark {
  --bg: black;
  --text: white;
}
```

The CSS uses CSS variables for theming.

## Verification
- **Test:** Form validation works
- **Test:** Modal traps focus
- **Test:** Infinite scroll loads
- **Live:** Performance is monitored
- **Audit:** Annual a11y audit

## Gotchas
- **The "form without validation" anti-pattern.** A form
  that accepts anything is a bug. Validate.
- **The "modal without focus trap" anti-pattern.** A modal
  that allows tabbing to the page is a bug.
- **The "infinite scroll without end" anti-pattern.** A
  list that loads forever is a bug. Set a max.
- **The "upload with no progress" anti-pattern.** The user
  doesn't know if the upload is working. Show progress.
- **The "dark mode without persistence" anti-pattern.** The
  user picks dark mode; refreshes; back to light. Persist.

## Related
- `feature-cookbook.md`
- `accessibility-wcag-detail.md`
- `accessibility-components.md`
- `state-management-client-side.md`
- `frontend-bundle-optimization.md`
- React Hook Form: https://react-hook-form.com/
- TanStack Query: https://tanstack.com/query/latest
