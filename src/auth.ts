import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import bcrypt from "bcryptjs";
import { db, initDb } from "@/lib/db";
import { nanoid } from "nanoid";

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email as string | undefined;
        const password = credentials?.password as string | undefined;
        if (!email || !password) return null;

        await initDb();
        const result = await db().execute({
          sql: "SELECT * FROM users WHERE email = ?",
          args: [email],
        });
        const user = result.rows[0] as unknown as {
          id: string; email: string; name: string | null; password_hash: string | null;
        } | undefined;

        if (!user || !user.password_hash) return null;
        const valid = await bcrypt.compare(password, user.password_hash);
        if (!valid) return null;

        return { id: user.id, email: user.email, name: user.name ?? undefined };
      },
    }),
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],

  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        if (!user.email) return false;
        await initDb();
        const existing = await db().execute({
          sql: "SELECT id FROM users WHERE email = ?",
          args: [user.email],
        });
        if (existing.rows.length === 0) {
          const id = nanoid();
          await db().execute({
            sql: "INSERT INTO users (id, email, name, created_at) VALUES (?, ?, ?, ?)",
            args: [id, user.email, user.name ?? null, Date.now()],
          });
          user.id = id;
        } else {
          user.id = existing.rows[0].id as string;
        }
      }
      return true;
    },

    async jwt({ token, user }) {
      if (user?.id) token.userId = user.id;
      return token;
    },

    async session({ session, token }) {
      if (token.userId) session.user.id = token.userId as string;
      return session;
    },
  },

  pages: {
    signIn: "/login",
  },

  session: { strategy: "jwt" },
});
