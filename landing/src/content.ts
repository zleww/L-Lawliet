// Everything specific to L-Lawliet lives here. The sections only read this file.
// Facts come from the site itself; no invented users, ratings or testimonials.
import { BookOpenText, Bookmark, LayoutGrid, MessagesSquare, Search, Share2 } from "lucide-react";
import type { Shot, SiteContent } from "./types";
import logo from "./assets/logo.webp";
import browse from "./assets/shots/ll-browse.webp";
import browseSm from "./assets/shots/ll-browse-960.webp";
import search from "./assets/shots/ll-search.webp";
import searchSm from "./assets/shots/ll-search-960.webp";
import detail from "./assets/shots/ll-detail.webp";
import detailSm from "./assets/shots/ll-detail-960.webp";
import notes from "./assets/shots/ll-notes.webp";
import notesSm from "./assets/shots/ll-notes-960.webp";
import home from "./assets/shots/ll-home.webp";
import homeSm from "./assets/shots/ll-home-960.webp";
import categories from "./assets/shots/ll-categories.webp";
import categoriesSm from "./assets/shots/ll-categories-960.webp";

const HOST = "l-lawliet-three.vercel.app";

const shots = {
  browse: { src: browse, small: browseSm, url: `${HOST}/browse`,
    alt: "L-Lawliet's Browse page: a search box, category filters and cards for Republic Acts such as RA 10175 and RA 10963." },
  search: { src: search, small: searchSm, url: `${HOST}/browse?q=data+privacy`,
    alt: "Searching 'data privacy' on L-Lawliet returns RA 10173, the Data Privacy Act." },
  detail: { src: detail, small: detailSm, url: `${HOST}/browse#ra-10175`,
    alt: "The page for RA 10175 with its quick summary, signing president, number of sections, minimum fine and who it covers." },
  notes: { src: notes, small: notesSm, url: `${HOST}/browse#ra-10175`,
    alt: "The bottom of a law page: why it matters, an example scenario, penalties, a link to the Official Gazette and community notes." },
  home: { src: home, small: homeSm, url: HOST,
    alt: "L-Lawliet's home page: 'Philippine laws, in plain English' with a search box and popular searches." },
  categories: { src: categories, small: categoriesSm, url: `${HOST}/categories`,
    alt: "The Categories page with six categories, from Technology & Crime to Education & Civil Rights." },
} satisfies Record<string, Shot>;

export const site: SiteContent = {
  name: "L-Lawliet",
  logo,
  logoAlt: "L-Lawliet",
  homeHref: "landing.html",
  nav: [
    { label: "Features", id: "features" },
    { label: "How it works", id: "how-it-works" },
    { label: "Demo", id: "showcase" },
    { label: "FAQ", id: "faq" },
  ],
  login: { label: "Log in", href: "login.html" },
  signup: { label: "Start reading free", href: "login.html?signup=1" },
  guest: { label: "Browse as a guest", href: "index.html?guest=1" },

  hero: {
    eyebrow: "For law and criminology students",
    headline: { before: "Read the law the way you", accent: "study", after: "it." },
    sub: "Every Republic Act broken down into what it requires, who it covers, a real-life example and the penalties. No legal jargon, and a link to the full text in the Official Gazette.",
    shot: shots.browse,
  },

  problem: {
    eyebrow: "Why L-Lawliet",
    title: "From a 30-page law to the part you need for class.",
    oldLabel: "The old way",
    oldCopy: "You open the Official Gazette the night before recitation, scroll past pages of definitions, and still can't say who the law covers or what happens if someone breaks it.",
    newLabel: "With L-Lawliet",
    points: [
      { title: "One page per law", text: "A short summary, why it matters, an example case and the penalties." },
      { title: "Search the way you remember it", text: "By RA number, title, signing president or topic." },
      { title: "Always check the source", text: "Every law links to its full text in the Official Gazette." },
      { title: "Study with classmates", text: "Notes and mnemonics on any law, with the helpful ones marked." },
    ],
  },

  features: {
    eyebrow: "Features",
    title: "Built for the night before a recitation.",
    sub: "Find the law, get the point, check the source.",
    items: [
      { icon: BookOpenText, title: "Plain-English breakdowns", text: "Each law split into what it requires, who it covers, an example and the penalties.", demo: "breakdown", span: 4 },
      { icon: Search, title: "Fast search", text: "RA number, title, president or topic.", demo: "search", span: 2 },
      { icon: LayoutGrid, title: "Six categories", text: "From Technology & Crime to Education & Civil Rights.", demo: "chips", span: 2 },
      { icon: MessagesSquare, title: "Community notes", text: "Post, edit and vote on notes and mnemonics.", demo: "notes", span: 2 },
      { icon: Bookmark, title: "Rate and save", text: "Rate laws, save them for later, and suggest laws to add.", demo: "rating", span: 2 },
      { icon: Share2, title: "One account, three sites", text: "Read it here, drill it on JurisCards, test it in the Arena. The same login works on all three.", demo: "account", span: 6 },
    ],
  },

  steps: {
    eyebrow: "How it works",
    title: "Three steps from question to answer.",
    items: [
      { title: "Find it fast", text: "Search by RA number, title, president or topic, or open one of six categories.", shot: shots.search },
      { title: "Read the plain version", text: "A quick summary, the signing president, the minimum fine and who the law covers, on one page.", shot: shots.detail },
      { title: "Learn from classmates", text: "Read why it matters and an example case, check the Official Gazette, then read and add notes.", shot: shots.notes },
    ],
  },

  stats: {
    title: "The database today",
    items: [
      { to: 31, label: "Republic Acts", live: "laws" },
      { to: 6, label: "Categories", live: "categories" },
      { to: 10, label: "Laws free without an account" },
      { to: 3, label: "Sites, one account" },
    ],
  },

  showcase: {
    eyebrow: "Demo",
    title: "See the real thing.",
    sub: "Screenshots of the live site, as a guest sees it.",
    tabs: [
      { label: "Home", caption: "Search first, with popular topics one click away.", shot: shots.home },
      { label: "Browse", caption: "Every law as a card, filterable by category.", shot: shots.browse },
      { label: "Categories", caption: "Six categories that cover the whole database.", shot: shots.categories },
      { label: "Law page", caption: "One law, broken down for class.", shot: shots.detail },
    ],
  },

  faq: [
    { q: "Is L-Lawliet free?", a: "Yes. Reading, searching and the account are free for students, with no ads and no credit card." },
    { q: "What can I do without an account?", a: "Guests can read the first 10 laws, search and browse by category, and read classmates' notes. A free account unlocks every law, posting and voting on notes, rating and saving laws, and suggesting laws to add." },
    { q: "Is this legal advice?", a: "No. The summaries are a study aid. Every law links to its full text in the Official Gazette, which is the version to rely on." },
    { q: "Does my account work on JurisCards and the Arena?", a: "Yes. The three sites share one database, so the same username and password, or Google sign-in, works on each of them." },
    { q: "I forgot my password. What now?", a: "Use \"Forgot password?\" on the login page. We email a reset link to the address on your account; it works once, for 30 minutes." },
  ],

  finalCta: {
    title: "Stop memorizing jargon. Start understanding the law.",
    sub: "Free for students. No credit card, no ads.",
  },

  footer: {
    description: "Philippine Republic Acts in plain English, for law and criminology students.",
    links: [
      { label: "Browse laws", href: "browse.html" },
      { label: "Categories", href: "categories.html" },
      { label: "About", href: "about.html" },
      { label: "Resources", href: "resources.html" },
      { label: "API docs", href: "api/docs" },
    ],
    sisters: [
      { label: "JurisCards", href: "https://juris-card.vercel.app/", note: "Flashcards and quizzes" },
      { label: "JurisCards Arena", href: "https://just-give-up-atp.vercel.app/", note: "A card game about the law" },
    ],
    github: "https://github.com/zleww/L-Lawliet",
    disclaimer: "Summaries are a study aid, not legal advice.",
    year: 2026,
  },

  statsApi: "/api/v1/stats",
};
