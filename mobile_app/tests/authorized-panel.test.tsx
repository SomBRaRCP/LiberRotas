import { createElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthorizedPanel } from '../src/components/authorized-panel';

const { useAppMock, paramsMock } = vi.hoisted(() => ({
  useAppMock: vi.fn(),
  paramsMock: vi.fn(),
}));

vi.mock('@/context/app-context', () => ({ useApp: useAppMock }));
vi.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
vi.mock('@/components/local-clock', () => ({ LocalClock: () => null }));
vi.mock('@/components/ui', () => ({
  LoadingScreen: () => createElement('p', null, 'Carregando acesso'),
  AppButton: ({ children }: { children: ReactNode }) => createElement('button', null, children),
}));
vi.mock('expo-router', () => ({
  Redirect: ({ href }: { href: string }) => createElement('a', { href }, 'Redirecionando'),
  router: { replace: vi.fn(), push: vi.fn() },
  useLocalSearchParams: paramsMock,
}));
vi.mock('react-native-safe-area-context', () => ({
  SafeAreaView: ({ children }: { children: ReactNode }) => createElement('main', null, children),
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

function session(overrides = {}) {
  return {
    isHydrated: true,
    isResolvingAccess: false,
    hasFirebaseSession: true,
    isAuthenticated: true,
    accessSession: { access_state: 'AUTHORIZED', role: 'admin' },
    accessDestination: '/admin',
    deviceApprovalRequired: false,
    hasPermission: () => true,
    logout: vi.fn(),
    ...overrides,
  };
}

const renderPrivateTool = vi.fn(() => createElement('p', null, 'Conteudo reservado'));

function renderPanel() {
  return renderToStaticMarkup(createElement(AuthorizedPanel, {
    role: 'admin',
    title: 'Painel administrativo',
    subtitle: 'Teste de autorizacao',
    sections: [{
      id: 'accounts',
      title: 'Gerenciar contas',
      description: 'Ferramenta restrita',
      icon: 'shield-checkmark-outline',
      permission: 'admin.accounts.read',
      additionalPermissions: ['admin.accounts.manage'],
      renderContent: renderPrivateTool,
    }],
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  paramsMock.mockReturnValue({ tool: 'accounts' });
  useAppMock.mockReturnValue(session());
});

describe('painel autorizado renderizado na Web', () => {
  it('aguarda a autorizacao sem renderizar a ferramenta restrita', () => {
    useAppMock.mockReturnValue(session({ isResolvingAccess: true }));
    expect(renderPanel()).toContain('Carregando acesso');
    expect(renderPrivateTool).not.toHaveBeenCalled();
  });

  it.each([
    [{ hasFirebaseSession: false }, '/login'],
    [{ isAuthenticated: false }, '/access-pending'],
    [{ deviceApprovalRequired: true }, '/account/devices'],
    [{ hasPermission: () => false }, '/access-pending'],
    [{ accessSession: { access_state: 'PENDING', role: 'admin' } }, '/access-pending'],
    [{ accessSession: { access_state: 'AUTHORIZED', role: 'visitor' }, accessDestination: '/' }, '/'],
  ])('redireciona uma sessao impedida de acessar o painel (%j)', (overrides, destination) => {
    useAppMock.mockReturnValue(session(overrides));
    expect(renderPanel()).toContain(`href="${destination}"`);
    expect(renderPrivateTool).not.toHaveBeenCalled();
  });

  it('exige todas as permissoes mesmo quando a URL pede a ferramenta', () => {
    useAppMock.mockReturnValue(session({
      hasPermission: (permission: string) => permission !== 'admin.accounts.manage',
    }));
    expect(renderPanel()).toContain('Nenhum recurso adicional foi liberado');
    expect(renderPrivateTool).not.toHaveBeenCalled();
  });

  it('renderiza a ferramenta quando sessao, funcao e permissoes estao autorizadas', () => {
    expect(renderPanel()).toContain('Conteudo reservado');
    expect(renderPrivateTool).toHaveBeenCalledOnce();
  });

  it('mantem as ferramentas fechadas ate uma selecao valida', () => {
    paramsMock.mockReturnValue({ tool: 'ferramenta-inexistente' });
    expect(renderPanel()).toContain('Gerenciar contas');
    expect(renderPrivateTool).not.toHaveBeenCalled();
  });
});
