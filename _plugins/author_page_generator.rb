module Jekyll
  class AuthorPage < Page
    def initialize(site, base, dir, author_name, author_slug, lang, filtered_posts)
      @site = site
      @base = base
      @dir = dir
      @name = "#{author_slug}.html"

      self.process(@name)
      self.read_yaml(File.join(base, '_layouts'), 'author.html')

      self.data['title'] = author_name
      self.data['author_name'] = author_name
      self.data['author_slug'] = author_slug
      self.data['lang'] = lang
      self.data['filtered_posts'] = filtered_posts
    end
  end

  class AuthorPageGenerator < Generator
    safe true
    priority :low

    def generate(site)
      # Collect all unique authors across all posts
      authors = {}

      site.posts.docs.each do |post|
        author = post.data['author']
        next if author.nil? || author.empty?

        slug = Utils.slugify(author)
        authors[slug] ||= { name: author, slug: slug }
      end

      # For each author, generate EN and ES pages
      authors.each_value do |author_info|
        ['en', 'es'].each do |lang|
          # Filter posts by language and author
          filtered = site.posts.docs.select do |post|
            post_lang = post.data['lang'] || 'en'
            post_author = post.data['author'] || ''
            post_lang == lang && Utils.slugify(post_author) == author_info[:slug]
          end

          # Sort by date descending
          filtered.sort_by! { |p| p.date }.reverse!

          next if filtered.empty?

          dir = File.join(lang, 'author')
          site.pages << AuthorPage.new(
            site,
            site.source,
            dir,
            author_info[:name],
            author_info[:slug],
            lang,
            filtered
          )
        end
      end
    end
  end
end
