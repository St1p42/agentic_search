import { EntityRow, InferredSchema, ResearchStage, Source } from '@/types';

export const mockSchema: InferredSchema = {
  entityType: 'AI Healthcare Startup',
  columns: [
    { key: 'name', label: 'Company', type: 'text' },
    { key: 'website', label: 'Website', type: 'url' },
    { key: 'description', label: 'Description', type: 'text' },
    { key: 'focus', label: 'Focus Area', type: 'text' },
    { key: 'headquarters', label: 'Headquarters', type: 'text' },
    { key: 'fundingStage', label: 'Funding Stage', type: 'text' },
  ],
};

export const mockRows: EntityRow[] = [
  {
    id: '1',
    name: {
      value: 'Tempus AI',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.tempus.com/about',
          domain: 'tempus.com',
          pageTitle: 'About Tempus | Precision Medicine',
          snippet: 'Tempus is a technology company advancing precision medicine through the practical application of artificial intelligence in healthcare.',
          sourceType: 'official',
          quality: 'high',
        },
        {
          sourceUrl: 'https://www.crunchbase.com/organization/tempus-3',
          domain: 'crunchbase.com',
          pageTitle: 'Tempus - Crunchbase Company Profile',
          snippet: 'Tempus is building the world\'s largest library of clinical and molecular data.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'tempus.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.tempus.com',
          domain: 'tempus.com',
          pageTitle: 'Tempus | Precision Medicine',
          snippet: 'Official website of Tempus AI healthcare company.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI-powered precision medicine platform combining genomic sequencing with clinical data analytics',
      confidence: 0.92,
      evidence: [
        {
          sourceUrl: 'https://www.tempus.com/about',
          domain: 'tempus.com',
          pageTitle: 'About Tempus',
          snippet: 'We have built the world\'s largest library of clinical and molecular data and an operating system to make that data accessible and useful.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Precision Medicine & Oncology',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.fiercehealthcare.com/health-tech/tempus-ai',
          domain: 'fiercehealthcare.com',
          pageTitle: 'Tempus brings AI to cancer treatment',
          snippet: 'The company focuses on using AI to analyze clinical and molecular data for cancer treatment optimization.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'Chicago, IL',
      confidence: 0.96,
      evidence: [
        {
          sourceUrl: 'https://www.linkedin.com/company/tempus-ai',
          domain: 'linkedin.com',
          pageTitle: 'Tempus | LinkedIn',
          snippet: 'Tempus is headquartered in Chicago, Illinois.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series G ($1.1B raised)',
      confidence: 0.91,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/tempus-3',
          domain: 'crunchbase.com',
          pageTitle: 'Tempus Funding Rounds',
          snippet: 'Tempus has raised $1.1 billion in funding over multiple rounds, most recently Series G.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '2',
    name: {
      value: 'Viz.ai',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.viz.ai/about',
          domain: 'viz.ai',
          pageTitle: 'About Viz.ai | AI-Powered Care Coordination',
          snippet: 'Viz.ai is the pioneer in the use of AI algorithms and machine learning to increase speed of diagnosis.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'viz.ai',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.viz.ai',
          domain: 'viz.ai',
          pageTitle: 'Viz.ai | Intelligent Care Coordination',
          snippet: 'Official website of Viz.ai healthcare AI company.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI-powered stroke detection and care coordination platform for hospitals',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.viz.ai/about',
          domain: 'viz.ai',
          pageTitle: 'About Viz.ai',
          snippet: 'Our AI-powered care coordination solution analyzes medical images to detect time-sensitive conditions.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Medical Imaging & Stroke Detection',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.healthcareitnews.com/viz-ai-stroke',
          domain: 'healthcareitnews.com',
          pageTitle: 'Viz.ai stroke detection AI gains traction',
          snippet: 'Viz.ai\'s FDA-cleared AI platform specializes in stroke detection from CT scans.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'San Francisco, CA',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.linkedin.com/company/viz-ai',
          domain: 'linkedin.com',
          pageTitle: 'Viz.ai | LinkedIn',
          snippet: 'Viz.ai is based in San Francisco, California.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series D ($250M raised)',
      confidence: 0.89,
      evidence: [
        {
          sourceUrl: 'https://techcrunch.com/viz-ai-funding',
          domain: 'techcrunch.com',
          pageTitle: 'Viz.ai raises $100M Series D',
          snippet: 'AI medical imaging startup Viz.ai has raised $100 million in Series D funding.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '3',
    name: {
      value: 'Recursion Pharmaceuticals',
      confidence: 0.96,
      evidence: [
        {
          sourceUrl: 'https://www.recursion.com/about',
          domain: 'recursion.com',
          pageTitle: 'About Recursion | Decoding Biology',
          snippet: 'Recursion is a clinical-stage biotechnology company decoding biology by integrating technological innovations.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'recursion.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.recursion.com',
          domain: 'recursion.com',
          pageTitle: 'Recursion | Decoding Biology',
          snippet: 'Official website of Recursion Pharmaceuticals.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI-driven drug discovery platform using computer vision and machine learning on cellular images',
      confidence: 0.91,
      evidence: [
        {
          sourceUrl: 'https://www.recursion.com/technology',
          domain: 'recursion.com',
          pageTitle: 'Our Technology | Recursion',
          snippet: 'We generate one of the world\'s largest biological and chemical datasets and use AI to discover new medicines.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'AI Drug Discovery',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.nature.com/articles/recursion-ai',
          domain: 'nature.com',
          pageTitle: 'AI in drug discovery: Recursion\'s approach',
          snippet: 'Recursion uses machine learning to accelerate the drug discovery process.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'Salt Lake City, UT',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/recursion-pharmaceuticals',
          domain: 'crunchbase.com',
          pageTitle: 'Recursion Pharmaceuticals',
          snippet: 'Recursion is headquartered in Salt Lake City, Utah.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Public (NASDAQ: RXRX)',
      confidence: 0.97,
      evidence: [
        {
          sourceUrl: 'https://www.nasdaq.com/market-activity/stocks/rxrx',
          domain: 'nasdaq.com',
          pageTitle: 'RXRX Stock Quote',
          snippet: 'Recursion Pharmaceuticals trades on NASDAQ under ticker RXRX.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '4',
    name: {
      value: 'PathAI',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.pathai.com/about',
          domain: 'pathai.com',
          pageTitle: 'About PathAI | AI-Powered Pathology',
          snippet: 'PathAI is the leading provider of AI-powered pathology technology.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'pathai.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.pathai.com',
          domain: 'pathai.com',
          pageTitle: 'PathAI | Transforming Pathology',
          snippet: 'Official website of PathAI.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI-powered pathology platform for accurate diagnosis and drug development',
      confidence: 0.92,
      evidence: [
        {
          sourceUrl: 'https://www.pathai.com/technology',
          domain: 'pathai.com',
          pageTitle: 'Our Technology | PathAI',
          snippet: 'PathAI develops machine learning technology to assist pathologists in making rapid, accurate diagnoses.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Digital Pathology & Diagnostics',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.mobihealthnews.com/pathai',
          domain: 'mobihealthnews.com',
          pageTitle: 'PathAI advances digital pathology',
          snippet: 'PathAI focuses on using AI to improve accuracy and efficiency in pathology diagnostics.',
          sourceType: 'article',
          quality: 'medium',
        },
      ],
    },
    headquarters: {
      value: 'Boston, MA',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.linkedin.com/company/pathai',
          domain: 'linkedin.com',
          pageTitle: 'PathAI | LinkedIn',
          snippet: 'PathAI is headquartered in Boston, Massachusetts.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series D ($165M raised)',
      confidence: 0.88,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/pathai',
          domain: 'crunchbase.com',
          pageTitle: 'PathAI Funding',
          snippet: 'PathAI has raised $165 million across multiple funding rounds.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '5',
    name: {
      value: 'Insitro',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.insitro.com/about',
          domain: 'insitro.com',
          pageTitle: 'About Insitro | Machine Learning for Drug Discovery',
          snippet: 'Insitro is rethinking drug development by integrating machine learning with biology at scale.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'insitro.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.insitro.com',
          domain: 'insitro.com',
          pageTitle: 'Insitro | ML-Driven Drug Discovery',
          snippet: 'Official website of Insitro.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'Machine learning-driven drug discovery company using high-content biology data',
      confidence: 0.91,
      evidence: [
        {
          sourceUrl: 'https://www.insitro.com/science',
          domain: 'insitro.com',
          pageTitle: 'Our Science | Insitro',
          snippet: 'We use machine learning to transform the way drugs are discovered and developed.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'ML Drug Discovery & Development',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.wired.com/story/insitro-ai-drug-discovery',
          domain: 'wired.com',
          pageTitle: 'Insitro bets on AI for drug discovery',
          snippet: 'Insitro combines machine learning with cellular biology to accelerate drug development.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'South San Francisco, CA',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/insitro',
          domain: 'crunchbase.com',
          pageTitle: 'Insitro | Crunchbase',
          snippet: 'Insitro is based in South San Francisco, California.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series C ($400M raised)',
      confidence: 0.90,
      evidence: [
        {
          sourceUrl: 'https://techcrunch.com/insitro-series-c',
          domain: 'techcrunch.com',
          pageTitle: 'Insitro raises $400M Series C',
          snippet: 'Insitro has raised $400 million in total funding, including a $400M Series C.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '6',
    name: {
      value: 'Butterfly Network',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.butterflynetwork.com/about',
          domain: 'butterflynetwork.com',
          pageTitle: 'About Butterfly Network',
          snippet: 'Butterfly Network created the first handheld, whole-body ultrasound system.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'butterflynetwork.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.butterflynetwork.com',
          domain: 'butterflynetwork.com',
          pageTitle: 'Butterfly Network | Ultrasound Reimagined',
          snippet: 'Official website of Butterfly Network.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'Handheld AI-powered ultrasound device with smartphone connectivity',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.butterflynetwork.com/butterfly-iq',
          domain: 'butterflynetwork.com',
          pageTitle: 'Butterfly iQ | Handheld Ultrasound',
          snippet: 'Butterfly iQ is a single-probe, whole-body ultrasound system that connects to your smartphone.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Portable Ultrasound & Diagnostics',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.statnews.com/butterfly-ultrasound',
          domain: 'statnews.com',
          pageTitle: 'Butterfly brings ultrasound to your pocket',
          snippet: 'The company focuses on making medical imaging accessible and affordable through portable ultrasound.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'Burlington, MA',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.linkedin.com/company/butterfly-network',
          domain: 'linkedin.com',
          pageTitle: 'Butterfly Network | LinkedIn',
          snippet: 'Butterfly Network is headquartered in Burlington, Massachusetts.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Public (NYSE: BFLY)',
      confidence: 0.97,
      evidence: [
        {
          sourceUrl: 'https://www.nyse.com/quote/XNYS:BFLY',
          domain: 'nyse.com',
          pageTitle: 'BFLY Stock Quote',
          snippet: 'Butterfly Network trades on NYSE under ticker BFLY.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '7',
    name: {
      value: 'Freenome',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.freenome.com/about',
          domain: 'freenome.com',
          pageTitle: 'About Freenome | Early Cancer Detection',
          snippet: 'Freenome is a biotech company using AI for early cancer detection through blood tests.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'freenome.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.freenome.com',
          domain: 'freenome.com',
          pageTitle: 'Freenome | Detecting Cancer Early',
          snippet: 'Official website of Freenome.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI-powered blood test for early cancer detection using multiomics',
      confidence: 0.92,
      evidence: [
        {
          sourceUrl: 'https://www.freenome.com/science',
          domain: 'freenome.com',
          pageTitle: 'Our Science | Freenome',
          snippet: 'We use a multiomics platform combined with AI to detect cancer at its earliest stages.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Cancer Screening & Liquid Biopsy',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.fiercebiotech.com/freenome-liquid-biopsy',
          domain: 'fiercebiotech.com',
          pageTitle: 'Freenome advances liquid biopsy technology',
          snippet: 'Freenome develops blood-based tests for early cancer detection using machine learning.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
    headquarters: {
      value: 'South San Francisco, CA',
      confidence: 0.94,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/freenome',
          domain: 'crunchbase.com',
          pageTitle: 'Freenome | Crunchbase',
          snippet: 'Freenome is headquartered in South San Francisco, California.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series D ($290M raised)',
      confidence: 0.89,
      evidence: [
        {
          sourceUrl: 'https://www.crunchbase.com/organization/freenome',
          domain: 'crunchbase.com',
          pageTitle: 'Freenome Funding',
          snippet: 'Freenome has raised approximately $290 million in funding.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
  },
  {
    id: '8',
    name: {
      value: 'Owkin',
      confidence: 0.93,
      evidence: [
        {
          sourceUrl: 'https://www.owkin.com/about',
          domain: 'owkin.com',
          pageTitle: 'About Owkin | AI for Medical Research',
          snippet: 'Owkin uses AI to find the right treatment for every patient.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    website: {
      value: 'owkin.com',
      confidence: 0.98,
      evidence: [
        {
          sourceUrl: 'https://www.owkin.com',
          domain: 'owkin.com',
          pageTitle: 'Owkin | AI for Life Sciences',
          snippet: 'Official website of Owkin.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    description: {
      value: 'AI and federated learning platform for drug discovery and diagnostics',
      confidence: 0.91,
      evidence: [
        {
          sourceUrl: 'https://www.owkin.com/technology',
          domain: 'owkin.com',
          pageTitle: 'Our Technology | Owkin',
          snippet: 'Owkin uses federated learning to train AI models on distributed medical data while preserving privacy.',
          sourceType: 'official',
          quality: 'high',
        },
      ],
    },
    focus: {
      value: 'Federated Learning & Drug Discovery',
      confidence: 0.92,
      evidence: [
        {
          sourceUrl: 'https://www.forbes.com/owkin-federated-learning',
          domain: 'forbes.com',
          pageTitle: 'Owkin brings federated learning to healthcare',
          snippet: 'The company specializes in federated learning approaches for healthcare AI.',
          sourceType: 'article',
          quality: 'medium',
        },
      ],
    },
    headquarters: {
      value: 'Paris, France',
      confidence: 0.95,
      evidence: [
        {
          sourceUrl: 'https://www.linkedin.com/company/owkin',
          domain: 'linkedin.com',
          pageTitle: 'Owkin | LinkedIn',
          snippet: 'Owkin is headquartered in Paris, France with offices in New York.',
          sourceType: 'profile',
          quality: 'high',
        },
      ],
    },
    fundingStage: {
      value: 'Series B ($180M raised)',
      confidence: 0.88,
      evidence: [
        {
          sourceUrl: 'https://techcrunch.com/owkin-series-b',
          domain: 'techcrunch.com',
          pageTitle: 'Owkin raises $180M Series B',
          snippet: 'French AI healthcare startup Owkin has raised $180 million in Series B funding.',
          sourceType: 'article',
          quality: 'high',
        },
      ],
    },
  },
];

export const mockStages: ResearchStage[] = [
  {
    id: 'planning',
    name: 'Planning schema',
    status: 'completed',
    startedAt: new Date(Date.now() - 45000),
    completedAt: new Date(Date.now() - 42000),
    details: {
      outputs: ['Inferred entity type: AI Healthcare Startup', 'Generated 6 columns'],
      counts: { columnsGenerated: 6 },
    },
  },
  {
    id: 'searching',
    name: 'Searching and reading web sources',
    status: 'completed',
    startedAt: new Date(Date.now() - 42000),
    completedAt: new Date(Date.now() - 28000),
    details: {
      counts: { pagesSearched: 47, pagesRead: 23 },
      topSources: ['crunchbase.com', 'techcrunch.com', 'linkedin.com', 'company websites'],
    },
  },
  {
    id: 'extracting',
    name: 'Extracting candidate entities',
    status: 'completed',
    startedAt: new Date(Date.now() - 28000),
    completedAt: new Date(Date.now() - 18000),
    details: {
      counts: { candidatesExtracted: 24, duplicatesRemoved: 8 },
    },
  },
  {
    id: 'assessing',
    name: 'Assessing sources and building evidence',
    status: 'completed',
    startedAt: new Date(Date.now() - 18000),
    completedAt: new Date(Date.now() - 10000),
    details: {
      counts: { sourcesAssessed: 23, highQuality: 18, mediumQuality: 5 },
    },
  },
  {
    id: 'fields',
    name: 'Extracting structured fields',
    status: 'completed',
    startedAt: new Date(Date.now() - 10000),
    completedAt: new Date(Date.now() - 4000),
    details: {
      counts: { fieldsExtracted: 48, confidenceAbove90: 42 },
    },
  },
  {
    id: 'finalizing',
    name: 'Finalizing result rows',
    status: 'completed',
    startedAt: new Date(Date.now() - 4000),
    completedAt: new Date(Date.now() - 1000),
    details: {
      outputs: ['Ranked and selected top 8 entities', 'Final confidence: 93%'],
      counts: { finalRows: 8 },
    },
  },
];

export const mockSources: Source[] = [
  {
    url: 'https://www.crunchbase.com/lists/ai-healthcare-startups',
    domain: 'crunchbase.com',
    title: 'AI Healthcare Startups - Companies',
    snippet: 'Discover the most innovative AI healthcare startups with funding data, investor information, and company details.',
    type: 'directory',
    fresh: true,
  },
  {
    url: 'https://www.tempus.com/about',
    domain: 'tempus.com',
    title: 'About Tempus | Precision Medicine',
    snippet: 'Tempus is a technology company advancing precision medicine through the practical application of artificial intelligence.',
    type: 'official',
    fresh: true,
  },
  {
    url: 'https://techcrunch.com/2024/ai-healthcare-funding',
    domain: 'techcrunch.com',
    title: 'AI healthcare startups raised record funding in 2024',
    snippet: 'The AI healthcare sector saw unprecedented investment with over $8 billion deployed across emerging startups.',
    type: 'article',
    fresh: true,
  },
  {
    url: 'https://www.linkedin.com/company/viz-ai',
    domain: 'linkedin.com',
    title: 'Viz.ai | LinkedIn',
    snippet: 'Viz.ai is the pioneer in AI-powered disease detection and care coordination. Based in San Francisco, CA.',
    type: 'profile',
    fresh: false,
  },
  {
    url: 'https://www.forbes.com/ai-50-healthcare',
    domain: 'forbes.com',
    title: 'Forbes AI 50: Healthcare Companies Leading Innovation',
    snippet: 'Our annual list of the most promising AI companies includes several healthcare innovators transforming patient care.',
    type: 'article',
    fresh: true,
  },
  {
    url: 'https://www.recursion.com/technology',
    domain: 'recursion.com',
    title: 'Our Technology | Recursion',
    snippet: 'We generate one of the world\'s largest biological datasets and use machine learning to discover new medicines.',
    type: 'official',
    fresh: true,
  },
];
