export type UiState = Readonly<{
  drawer: 'closed' | 'open';
  focusedId: string | null;
  mapEnabled: boolean;
}>;

export type UiAction =
  | Readonly<{ type: 'drawer/open' }>
  | Readonly<{ type: 'drawer/close' }>
  | Readonly<{ type: 'focus/set'; id: string }>
  | Readonly<{ type: 'focus/clear' }>
  | Readonly<{ type: 'map/set-enabled'; enabled: boolean }>;

function assertNever(value: never): never { throw new Error(`Unhandled UI action: ${JSON.stringify(value)}`); }

export function reduceUi(state: UiState, action: UiAction): UiState {
  switch (action.type) {
    case 'drawer/open': return { ...state, drawer: 'open' };
    case 'drawer/close': return { ...state, drawer: 'closed' };
    case 'focus/set': return { ...state, focusedId: action.id };
    case 'focus/clear': return { ...state, focusedId: null };
    case 'map/set-enabled': return { ...state, mapEnabled: action.enabled };
    default: return assertNever(action);
  }
}

export const initialUiState: UiState = { drawer: 'closed', focusedId: null, mapEnabled: false };
