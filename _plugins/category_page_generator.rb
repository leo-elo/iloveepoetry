module Jekyll
  class CategoryPage < Page
    def initialize(site, base, dir, category_name, category_slug, lang, filtered_posts)
      @site = site
      @base = base
      @dir = dir
      @name = "#{category_slug}.html"

      self.process(@name)
      self.read_yaml(File.join(base, '_layouts'), 'category.html')

      self.data['title'] = category_name
      self.data['category_name'] = category_name
      self.data['category_slug'] = category_slug
      self.data['lang'] = lang
      self.data['filtered_posts'] = filtered_posts
    end
  end

  class CategoryPageGenerator < Generator
    safe true
    priority :low

    def generate(site)
      # Collect all unique categories across all posts
      categories = {}

      site.posts.docs.each do |post|
        post.data['categories'].each do |cat|
          slug = Utils.slugify(cat)
          categories[slug] ||= { name: cat, slug: slug }
        end
      end

      # For each category, generate EN and ES pages
      categories.each_value do |cat_info|
        ['en', 'es'].each do |lang|
          # Filter posts by language and category
          filtered = site.posts.docs.select do |post|
            post_lang = post.data['lang'] || 'en'
            post_cats = (post.data['categories'] || []).map { |c| Utils.slugify(c) }
            post_lang == lang && post_cats.include?(cat_info[:slug])
          end

          # Sort by date descending
          filtered.sort_by! { |p| p.date }.reverse!

          dir = File.join(lang, 'category')
          site.pages << CategoryPage.new(
            site,
            site.source,
            dir,
            cat_info[:name],
            cat_info[:slug],
            lang,
            filtered
          )
        end
      end
    end
  end
end
