import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
  type RulesTestEnvironment,
} from '@firebase/rules-unit-testing';
import {
  deleteDoc,
  doc,
  getDoc,
  setDoc,
  updateDoc,
  type Firestore,
} from 'firebase/firestore';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest';

const PROJECT_ID = 'demo-liberrotas';
const EMULATOR_HOST = process.env.FIRESTORE_EMULATOR_HOST;
const describeWithEmulator = EMULATOR_HOST ? describe : describe.skip;

let testEnvironment: RulesTestEnvironment;

function authenticatedDb(
  userId: string,
  token: Record<string, unknown> = {},
): Firestore {
  return testEnvironment.authenticatedContext(userId, token).firestore();
}

function unauthenticatedDb(): Firestore {
  return testEnvironment.unauthenticatedContext().firestore();
}

async function seedDocument(path: string, data: Record<string, unknown>) {
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    await setDoc(doc(context.firestore(), path), data);
  });
}

function networkInteraction(userId: string) {
  return {
    userId,
    targetId: 'target-1',
    kind: 'favorite',
    createdAtMs: 1,
    privacy: {
      lgpdNoticeVersion: '1',
      syncedAtMs: 1,
      minimizedFields: ['userId', 'targetId', 'kind'],
    },
  };
}

function curatedPlace(status: 'approved' | 'pending') {
  return {
    ownerId: 'entrepreneur-1',
    createdBy: 'entrepreneur-1',
    ownerName: 'Empreendedor Teste',
    name: 'Feira Teste',
    address: 'Rua de Teste, 100',
    category: 'feiras_livres',
    latitude: -25.44,
    longitude: -49.19,
    createdAtMs: 1,
    status,
  };
}

describeWithEmulator('regras do Firestore', () => {
  beforeAll(async () => {
    const [host, portText] = EMULATOR_HOST!.split(':');
    const port = Number(portText);

    if (!host || !Number.isInteger(port)) {
      throw new Error(
        'FIRESTORE_EMULATOR_HOST deve usar o formato host:porta.',
      );
    }

    testEnvironment = await initializeTestEnvironment({
      projectId: PROJECT_ID,
      firestore: {
        host,
        port,
        rules: readFileSync(resolve(process.cwd(), 'firestore.rules'), 'utf8'),
      },
    });
  });

  beforeEach(async () => {
    await testEnvironment.clearFirestore();
  });

  afterAll(async () => {
    await testEnvironment.cleanup();
  });

  it('nega acesso anonimo e permite leituras publicas somente autenticadas', async () => {
    await seedDocument('public_profiles/visitor-1', {
      userId: 'visitor-1',
      displayName: 'Visitante Teste',
    });
    await seedDocument('posts/post-1', {
      authorId: 'visitor-1',
      text: 'Publicacao de teste',
    });
    await seedDocument('live_fairs/fair-1', {
      ownerId: 'entrepreneur-1',
      status: 'live',
    });

    const anonymous = unauthenticatedDb();
    const visitor = authenticatedDb('visitor-1', { role: 'visitor' });

    await assertFails(getDoc(doc(anonymous, 'public_profiles/visitor-1')));
    await assertFails(getDoc(doc(anonymous, 'posts/post-1')));
    await assertFails(getDoc(doc(anonymous, 'live_fairs/fair-1')));
    await assertFails(
      setDoc(doc(anonymous, 'coupon_validations/anonymous'), {
        userId: 'visitor-1',
      }),
    );

    await assertSucceeds(getDoc(doc(visitor, 'public_profiles/visitor-1')));
    await assertSucceeds(getDoc(doc(visitor, 'posts/post-1')));
    await assertSucceeds(getDoc(doc(visitor, 'live_fairs/fair-1')));
  });

  it('bloqueia escritas de cliente nas colecoes controladas pelo backend', async () => {
    const entrepreneur = authenticatedDb('entrepreneur-1', {
      role: 'entrepreneur',
    });

    await assertFails(
      setDoc(doc(entrepreneur, 'public_profiles/entrepreneur-1'), {
        userId: 'entrepreneur-1',
      }),
    );
    await assertFails(
      setDoc(doc(entrepreneur, 'posts/post-client'), {
        authorId: 'entrepreneur-1',
      }),
    );
    await assertFails(
      setDoc(
        doc(entrepreneur, 'curated_places/place-client'),
        curatedPlace('approved'),
      ),
    );
    await assertFails(
      setDoc(doc(entrepreneur, 'live_fairs/fair-client'), {
        ownerId: 'entrepreneur-1',
      }),
    );

    await seedDocument('posts/post-existing', {
      authorId: 'entrepreneur-1',
      text: 'Original',
    });
    await assertFails(
      updateDoc(doc(entrepreneur, 'posts/post-existing'), { text: 'Alterado' }),
    );
    await assertFails(deleteDoc(doc(entrepreneur, 'posts/post-existing')));
  });

  it('restringe private_profiles ao proprietario empreendedor', async () => {
    const entrepreneur = authenticatedDb('entrepreneur-1', {
      role: 'entrepreneur',
    });
    const otherEntrepreneur = authenticatedDb('entrepreneur-2', {
      role: 'entrepreneur',
    });
    const visitor = authenticatedDb('visitor-1', { role: 'visitor' });
    const ownProfile = doc(entrepreneur, 'private_profiles/entrepreneur-1');

    await assertSucceeds(
      setDoc(ownProfile, {
        userId: 'entrepreneur-1',
        pixKey: 'pix@example.com',
        updatedAtMs: 1,
      }),
    );
    await assertSucceeds(getDoc(ownProfile));
    await assertSucceeds(
      updateDoc(ownProfile, { pixKey: 'pix-atualizada@example.com', updatedAtMs: 2 }),
    );

    await assertFails(
      setDoc(doc(visitor, 'private_profiles/visitor-1'), {
        userId: 'visitor-1',
        pixKey: 'pix-visitante@example.com',
        updatedAtMs: 1,
      }),
    );
    await assertFails(
      getDoc(doc(otherEntrepreneur, 'private_profiles/entrepreneur-1')),
    );
    await assertFails(
      setDoc(doc(otherEntrepreneur, 'private_profiles/entrepreneur-1'), {
        userId: 'entrepreneur-2',
        pixKey: 'pix-outro@example.com',
        updatedAtMs: 1,
      }),
    );
    await assertSucceeds(deleteDoc(ownProfile));
  });

  it('protege network_interactions por usuario e valida o payload', async () => {
    const visitor = authenticatedDb('visitor-1', { role: 'visitor' });
    const otherVisitor = authenticatedDb('visitor-2', { role: 'visitor' });
    const ownInteraction = doc(visitor, 'network_interactions/interaction-1');

    await assertSucceeds(
      setDoc(ownInteraction, networkInteraction('visitor-1')),
    );
    await assertSucceeds(getDoc(ownInteraction));
    await assertSucceeds(
      updateDoc(ownInteraction, { targetId: 'target-2', createdAtMs: 2 }),
    );
    await assertFails(
      setDoc(
        doc(visitor, 'network_interactions/spoofed'),
        networkInteraction('visitor-2'),
      ),
    );
    await assertFails(
      setDoc(doc(visitor, 'network_interactions/invalid-kind'), {
        ...networkInteraction('visitor-1'),
        kind: 'admin_grant',
      }),
    );
    await assertFails(
      getDoc(doc(otherVisitor, 'network_interactions/interaction-1')),
    );
    await assertFails(
      deleteDoc(doc(otherVisitor, 'network_interactions/interaction-1')),
    );
    await assertSucceeds(deleteDoc(ownInteraction));
  });

  it('permite criar e ler coupon_validations apenas para o proprio usuario', async () => {
    const visitor = authenticatedDb('visitor-1', { role: 'visitor' });
    const otherVisitor = authenticatedDb('visitor-2', { role: 'visitor' });
    const ownValidation = doc(visitor, 'coupon_validations/validation-1');

    await assertSucceeds(
      setDoc(ownValidation, {
        userId: 'visitor-1',
        couponId: 'coupon-1',
        validatedAtMs: 1,
      }),
    );
    await assertSucceeds(getDoc(ownValidation));
    await assertFails(
      setDoc(doc(visitor, 'coupon_validations/spoofed'), {
        userId: 'visitor-2',
        couponId: 'coupon-2',
      }),
    );
    await assertFails(getDoc(doc(otherVisitor, 'coupon_validations/validation-1')));
    await assertFails(
      updateDoc(ownValidation, { validatedAtMs: 2 }),
    );
    await assertFails(deleteDoc(ownValidation));
  });

  it('expoe somente curated_places aprovados para usuarios autenticados', async () => {
    await seedDocument('curated_places/approved-place', curatedPlace('approved'));
    await seedDocument('curated_places/pending-place', curatedPlace('pending'));

    const anonymous = unauthenticatedDb();
    const visitor = authenticatedDb('visitor-1', { role: 'visitor' });

    await assertFails(getDoc(doc(anonymous, 'curated_places/approved-place')));
    await assertSucceeds(getDoc(doc(visitor, 'curated_places/approved-place')));
    await assertFails(getDoc(doc(visitor, 'curated_places/pending-place')));
  });

  it('nega admin_users e o wildcard mesmo com claims administrativas', async () => {
    await seedDocument('admin_users/admin-1', { enabled: true });
    await seedDocument('unknown_collection/document-1', { visible: true });

    const admin = authenticatedDb('admin-1', {
      role: 'admin',
      admin: true,
    });

    await assertFails(getDoc(doc(admin, 'admin_users/admin-1')));
    await assertFails(
      setDoc(doc(admin, 'admin_users/admin-2'), { enabled: true }),
    );
    await assertFails(
      getDoc(doc(admin, 'unknown_collection/document-1')),
    );
    await assertFails(
      setDoc(doc(admin, 'unknown_collection/document-2'), { visible: true }),
    );
  });
});
