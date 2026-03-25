module Jekyll
  class AuthorPage < Page
    def initialize(site, base, dir, author_name, author_slug, lang)
      @site = site
      @base = base
      @dir = dir
      @name = "#{author_slug}.html"

      self.process(@name)

      self.data = {
        'layout' => 'author',
        'title' => author_name,
        'author_name' => author_name,
        'author_slug' => author_slug,
        'lang' => lang,
      }
      self.content = ''
    end
  end

  class AuthorPageGenerator < Generator
    safe true
    priority :low

    def generate(site)
      authors = {}

      site.posts.docs.each do |post|
        author = post.data['author']
        next if author.nil? || author.empty?

        slug = Utils.slugify(author)
        authors[slug] ||= { name: author, slug: slug }
      end

      authors.each_value do |author_info|
        ['en', 'es'].each do |lang|
          dir = File.join(lang, 'author')
          site.pages << AuthorPage.new(
            site,
            site.source,
            dir,
            author_info[:name],
            author_info[:slug],
            lang
          )
        end
      end
    end
  end
end
