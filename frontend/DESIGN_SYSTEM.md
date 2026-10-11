# Frontend design foundation (phase 2)

## Preview

Run `npm run dev` from `frontend`, then open `/design-system.html`.
`npm run build` builds both the application and the standalone preview;
`npm run preview` serves the built pages.

The preview is an independent HTML entry, **not a new Vue Router route**.
It imports no API, auth store or business view. Its contract content is labelled
as sample data; toggling a suggestion never saves anything.

## Integration boundary

The application imports `src/styles/main.css`. Phase 3's shell now shares the
tokens, local font and opt-in Element Plus bridge, but keeps legacy page-specific
rules. `application-shell.css` is scoped to the new shell and its teleported panels.
The preview imports `src/styles/design-system.css`, which composes:

- `tokens.css`: colors, typography, spacing, radii, motion and responsive tokens.
- `fonts.css` (via `base.css`): local Inter, also shared with the application.
- `base.css`: reset, visible focus, reveal and reduced-motion rules (preview only).
- `element-plus.css`: opt-in `.design-system` theme bridge.

Phase 3 will explicitly redesign each business page using these foundations.
Do not import both global stylesheets into the application without resolving
the existing global rules. The accent remains the existing blue `#2563EB`.
The original shield/check silhouette is retained in `BrandLogo.vue`.
Inter is self-hosted with `font-display: swap`; its OFL license is included.

## Phase 3: application shell

- `views/Layout.vue`: composition only; existing auth fetch/logout and router kept.
- `components/layout/navigation.ts`: existing menu paths/labels and admin visibility.
- `components/layout/AppNavbar.vue`: fixed header, review shortcut, account menu.
- `components/layout/AppSidebar.vue`: keyboard-accessible router links and context panel.
- `components/layout/AppFooter.vue`: existing product/version information.
- Mobile navigation uses the existing Element Plus drawer for focus trapping,
  Escape and focus restoration. It closes on navigation or desktop breakpoint.
- Oversized legacy business content scrolls inside the workspace until its own pass.
- Fixed branding copy names no specific university. Contract/evidence data is unchanged.

## Phase 3: login and registration

- `views/LoginView.vue`: responsive product introduction and authentication card;
  existing fields, validation, store actions, messages and redirect are unchanged.
- `components/auth/AuthProductVisual.vue`: CSS/SVG-only LangGraph flow illustration,
  not a fabricated review result. No image request, new dependency or fake customer.
- Native form submission supports Enter without separate keyup/click submissions.
  Visible labels and username/password autocomplete are provided for both forms.
- `components/auth/AuthPasswordInput.vue`: replaces the library's mouse-only eye
  icon with a labelled native button supporting Tab, Enter and Space.
- `components/auth/AuthUsernameInput.vue`: keyboard-operable clear button which
  returns focus to the input after clearing; no username processing is added.
- Authentication remains immediately visible, without delayed entrance animations.
  Only decorative introduction elements and one-shot feature reveals animate.
- Login tests execute the actual setup handlers with stubbed store/router dependencies.

## UI components

| Component | Props | Notes |
| --- | --- | --- |
| AppContainer | as, width | 1280px / 720px; responsive gutters |
| AppSection | tone, spacing | Semantic section; default/muted/inverse |
| AppTypography | as, variant, tone | Semantic tag independent of visual size |
| AppButton | variant, size, loading, disabled, nativeType, href | Existing Element Plus; anchor for navigation |
| AppCard | as, tone, padding | Border and background; no resting shadow |

Use `data-reveal` inside the element returned by `useReveal()` for a one-time
IntersectionObserver entrance. Content stays visible if observers are unavailable.
The hero heading is never hidden for entrance animation. Reduced motion disables
decorative motion and immediately reveals content.

## Verification

- `npm test`: native Node regression tests, no API/network/key or added test library.
  The VM flag is test-only and currently emits Node's experimental warning.
- `npm run lint`: ESLint, including the preview and regression tests.
- `npm run build`: TypeScript and both Vite HTML entries.

Responsive targets: 320, 375, 390, 640, 768, 1024, 1280 and 1440px.
Keyboard checks: skip link, mobile menu Escape/focus return, navigation anchors,
content selectors and reversible sample acceptance. Respect reduced motion.

The existing large Element Plus chunk warning remains; dependency/chunk redesign
is outside this foundation phase. No new UI or animation libraries were added.
